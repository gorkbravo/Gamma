"""Regressions discovered by the budgeted Checkpoint 10 live acceptance."""
import pandas as pd
import pytest

from test_copilot import _build_test_client
from src.application.copilot_service import CopilotService
from src.models.copilot import CopilotContextBundle


@pytest.mark.parametrize('prompt', [
    'What is the fair value of LMT? Run DCF sensitivity and state temporary assumptions.',
    'Explain LMT DCF assumptions and inspect the dataset.',
])
def test_valuation_assumptions_do_not_request_saved_dcf_mutation(prompt):
    assert not CopilotService._prompt_requests_dcf_mutation(prompt.lower())
    assert CopilotService._prompt_requests_dcf_mutation('set lmt base dcf wacc to 9%')


def test_explicit_hypothetical_shock_keeps_acquisition_tools(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        result = client.post('/copilot/operator-plan', json={
            'domain':'synthesis', 'role':'research_operator',
            'prompt':'Stress a hypothetical portfolio of 60% SPY and 40% TLT with a +100 bps rate shock and -10% equity shock. Use exact supported parameters.',
            'selected_scope_domains':['research','risk'],
            'context':{'current_tab':'copilot'},
        }).json()
        assert result['intent'] == 'hypothetical_portfolio_comparison'
        assert [s['tool_id'] for s in result['steps']] == [
            'run_hypothetical_portfolio_comparison','run_risk_scenario_analysis',
        ]
        assert not result['confirmation_checkpoints']
    finally:
        runtime.shutdown()


def test_hypothetical_comparison_bounds_oversupplied_provider_history(tmp_path):
    _, runtime = _build_test_client(tmp_path)
    try:
        dates = pd.date_range('2025-01-01', periods=320, freq='B')
        # Early loss must not enter the explicitly requested newest window.
        prices = pd.Series([200.0 - i for i in range(60)] + [140.0 * 1.001**i for i in range(260)], index=dates)
        runtime.research_provider.load_prices = lambda snapshot, **kwargs: (
            {p.resolved_instrument_id():prices for p in snapshot.positions}, [])
        runtime.research_provider.load_benchmark_history = lambda *args, **kwargs: prices
        output = runtime.copilot_service._tool_run_hypothetical_portfolio_comparison({
            'legs':[{'symbol':'SPY','weight':.6},{'symbol':'TLT','weight':.4}],
            'benchmark_symbol':'SPY','lookback_days':252,'min_observations':100,
            'include_risk_analysis':False,
        }, CopilotContextBundle(domain='synthesis',current_tab='copilot',summary_data={})).output
        assert output['coverage']['aligned_observation_count'] == 252
        assert pd.Timestamp(output['coverage']['overlap_start']) == dates[-252]
        assert output['left']['metrics']['total_return'] > 0
    finally:
        runtime.shutdown()


def test_large_observation_keeps_other_exact_analytical_results():
    outputs = {'large':{'rows':['x'*1000]*100},
               'dcf':{'wacc_pct':.09,'fair_value_per_share':412.0},
               'reverse':{'implied_growth':.08,'warnings':['Mapping incomplete']}}
    bounded, retention = CopilotService._bounded_operator_outputs(outputs, {}, max_bytes=1000)
    assert retention['mode'] == 'compact'
    assert bounded['large']['truncated']
    assert bounded['dcf'] == outputs['dcf']
    assert bounded['reverse'] == outputs['reverse']
    assert CopilotService._json_size_bytes(bounded) <= 1000


@pytest.mark.parametrize('hv,expected', [(.12, 'ok'), (None, 'missing_historical_volatility'), (float('nan'), 'missing_historical_volatility'), (float('inf'), 'missing_historical_volatility'), (-1, 'missing_historical_volatility')])
def test_underlying_historical_volatility_preserves_provider_basis(tmp_path, hv, expected):
    _, runtime = _build_test_client(tmp_path)
    try:
        output = runtime.copilot_service._options_realized_implied_summary(
            surface={'symbol':'SPY', 'snapshot_available':True, 'underlying_historical_volatility':hv,
                     'expiry_analytics':[{'expiry':'20261016', 'atm_blended_implied_volatility':.2}],
                     'contracts':[]},
            normalized={'symbol':'SPY', 'max_expiries':1}, service_warnings=[], service_messages=[])
        row = output['expiry_comparisons'][0]
        assert row['comparison_status'] == expected
        if expected == 'ok':
            assert row['volatility_premium'] == pytest.approx(.08)
            assert row['implied_to_historical_ratio'] == pytest.approx(.2/.12)
            assert '30-day' in row['historical_volatility_basis']
            assert 'not matched' in row['historical_volatility_basis']
            assert any('estimator' in warning for warning in output['warnings'])
        else:
            assert row['volatility_premium'] is None
    finally:
        runtime.shutdown()


def test_filing_summary_usage_survives_store_and_api_roundtrip(tmp_path):
    from src.models.fundamentals import FundamentalsCompanySummaryRecord
    from src.application.fundamentals_service import _company_summary_to_payload, _company_summary_from_payload
    from src.services.fundamentals_store import FundamentalsResearchStore
    from src.api.schemas.fundamentals import FundamentalsCompanySummaryModel
    usage = {'response_id':'resp_test', 'status':'completed', 'usage':{
        'input_tokens':100, 'output_tokens':20, 'input_tokens_details':{'cached_tokens':40},
        'cache_write_tokens':30, 'output_tokens_details':{'reasoning_tokens':5}}}
    store = FundamentalsResearchStore(tmp_path)
    record = FundamentalsCompanySummaryRecord(ticker='LMT', model_usage=usage)
    store.save_company_summary('LMT', 'test', _company_summary_to_payload(record))
    restored = _company_summary_from_payload(store.load_company_summary('LMT', 'test'))
    assert FundamentalsCompanySummaryModel.from_domain(restored).model_usage == usage
    assert _company_summary_from_payload({'ticker':'LMT'}).model_usage == {}


def test_options_acronyms_are_not_implicit_equity_symbols():
    from src.application.copilot_entity_resolution import extract_explicit_equity_tickers
    assert extract_explicit_equity_tickers('Compare SPY ATM IV without preloaded UI') == ['SPY']
    assert extract_explicit_equity_tickers('Research $UI and ticker ATM') == ['UI', 'ATM']


def test_oil_delivery_month_is_distinct_from_last_trading_date(tmp_path):
    from types import SimpleNamespace
    from src.services.commodities_adapters import _ibkr_contract_month_label, _ibkr_contract_expiry
    contract = SimpleNamespace(lastTradeDateOrContractMonth='20261120', localSymbol='CLZ6')
    detail = SimpleNamespace(contractMonth='202612', realExpirationDate='20261120')
    assert _ibkr_contract_month_label(contract, detail) == 'Dec 2026'
    assert _ibkr_contract_expiry(contract, detail).strftime('%Y%m%d') == '20261120'
    from src.services.cache import CacheService
    from src.services.commodities_adapters import IbkrCommoditiesDataProvider, IBKR_FUTURES_ROOTS
    provider = object.__new__(IbkrCommoditiesDataProvider)
    provider.cache = CacheService(tmp_path)
    provider.contract_cache_seconds = 600
    config = IBKR_FUTURES_ROOTS[0]
    provider._store_contracts(config, [(contract, detail)])
    restored_contract, restored_detail = provider._cached_contracts(config)[0]
    assert _ibkr_contract_month_label(restored_contract, restored_detail) == 'Dec 2026'
    assert _ibkr_contract_expiry(restored_contract, restored_detail).strftime('%Y%m%d') == '20261120'


@pytest.mark.parametrize('reverse', [False, True])
def test_inventory_changes_follow_chronological_levels(reverse):
    from datetime import datetime
    from src.services.commodities_adapters import EiaCommoditiesDataProvider, EIA_INVENTORY_SERIES
    provider = EiaCommoditiesDataProvider(api_key='fixture')
    rows = [{'period':'2026-09-11', 'value':100}, {'period':'2026-09-18','value':110}, {'period':'2026-09-25','value':108}]
    provider._get_eia_payload = lambda *args, **kwargs: ({'response':{'data':list(reversed(rows)) if reverse else rows}}, datetime(2026,10,6))
    series = provider._fetch_eia_inventory_series(EIA_INVENTORY_SERIES[0])
    assert [point.change for point in series.points] == [None,10,-2]


def test_audit_preserves_usage_and_uncertain_cancellation_without_secrets(tmp_path, monkeypatch):
    import json
    from src.services.openai_usage_audit import audit_response
    monkeypatch.setenv('GAMMA_OPENAI_USAGE_AUDIT_DIR', str(tmp_path))
    with audit_response('test', 'fixture') as audit:
        audit.observe({'id':'resp_done','status':'completed','usage':{'input_tokens':10, 'output_tokens':5}, 'output':'private'})
    with pytest.raises(RuntimeError):
        with audit_response('test', 'fixture') as audit:
            audit.observe({'id':'resp_cancel','status':'in_progress'})
            raise RuntimeError('private secret error')
    records = [json.loads(path.read_text()) for path in tmp_path.glob('*.json')]
    complete = next(row for row in records if row.get('id') == 'resp_done')
    cancelled = next(row for row in records if row.get('id') == 'resp_cancel')
    assert complete['charge_status'] == 'provider_usage_reported'
    assert cancelled['charge_status'] == 'unknown' and cancelled['usage'] is None
    assert cancelled['error_type'] == 'RuntimeError'
    assert 'private' not in json.dumps(records)


def test_unloaded_options_acquisition_carries_underlying_hv_to_tool_and_api(tmp_path):
    from src.application.iv_service import IVSurfaceResult
    from src.api.schemas.iv import IVSurfaceResponseModel
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = runtime.iv_service._mock_snapshot('SPY', depth_preset='compact', surface_model='linear')
        snapshot.underlying_historical_volatility = .13
        requests = []
        def surface(request):
            requests.append(request)
            return IVSurfaceResult(snapshot=snapshot)
        runtime.iv_service.get_surface = surface
        output = runtime.copilot_service._tool_run_options_realized_implied_comparison(
            {'symbol':'SPY'}, CopilotContextBundle(domain='iv', current_tab='copilot', summary_data={}))
        assert requests[0].wait_seconds == 20
        assert output.output['expiry_comparisons']
        assert all(row['historical_volatility'] == .13 for row in output.output['expiry_comparisons'])
        assert IVSurfaceResponseModel.from_service_result('SPY', surface(requests[0])).underlying_historical_volatility == .13
        runtime.copilot_service.provider.stream_research_operator = lambda **kwargs: None
        plan = client.post('/copilot/research-plan', json={'domain':'synthesis', 'role':'research_operator',
            'prompt':'Run options realized versus implied comparison for SPY.',
            'selected_scope_domains':['iv'], 'context':{'current_tab':'copilot'}})
        assert plan.status_code == 200
        assert plan.json()['max_elapsed_ms'] == 90_000
    finally:
        runtime.shutdown()


def test_stream_audit_records_response_identity_before_cancellation(tmp_path, monkeypatch):
    import json
    from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider
    from src.services.copilot_provider import CopilotRunCancelled
    monkeypatch.setenv('GAMMA_OPENAI_USAGE_AUDIT_DIR', str(tmp_path))
    provider = OpenAIResponsesCopilotProvider(api_key='fixture', model='fixture', reasoning_effort='low')
    provider._open_stream = lambda payload: iter([{'type':'response.created', 'response':{'id':'resp_pending','status':'in_progress'}}])
    with pytest.raises(CopilotRunCancelled):
        provider._post_json_stream({'model':'fixture'}, lambda *args: None, lambda: True)
    record = json.loads(next(tmp_path.glob('*.json')).read_text())
    assert record['id'] == 'resp_pending'
    assert record['usage'] is None and record['charge_status'] == 'unknown'

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

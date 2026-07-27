from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
import logging
import threading
from typing import Dict, List, Optional, Tuple

from ib_insync import IB, Contract

from src.models.instruments import build_instrument_id
from src.models.portfolio import PortfolioSnapshot, PositionItem
from src.services.fx import FXService
from src.services.ib_thread import IBTaskTimeoutError, IBThreadBusyError, IBThreadRunner
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.utils.time import now_utc


logger = logging.getLogger(__name__)


PORTFOLIO_QUOTE_TIMEOUT_MIN_SECONDS = 0.1
PORTFOLIO_QUOTE_TIMEOUT_MAX_SECONDS = 10.0
PORTFOLIO_SNAPSHOT_BASE_WORK_SECONDS = 15.0
PORTFOLIO_SNAPSHOT_COMPLETION_MARGIN_SECONDS = 3.0
PORTFOLIO_SNAPSHOT_WORKER_TIMEOUT_CAP_SECONDS = 45.0


def validate_portfolio_quote_timeout(value: float) -> float:
    timeout = float(value)
    if not PORTFOLIO_QUOTE_TIMEOUT_MIN_SECONDS <= timeout <= PORTFOLIO_QUOTE_TIMEOUT_MAX_SECONDS:
        raise ValueError(
            "Portfolio quote timeout must be between "
            f"{PORTFOLIO_QUOTE_TIMEOUT_MIN_SECONDS:.1f} and "
            f"{PORTFOLIO_QUOTE_TIMEOUT_MAX_SECONDS:.1f} seconds."
        )
    return timeout


def derive_portfolio_snapshot_worker_timeout(
    quote_timeout_seconds: float,
    market_data_mode: str,
) -> float:
    quote_timeout = validate_portfolio_quote_timeout(quote_timeout_seconds)
    quote_passes = 2.0 if str(market_data_mode or "").strip().lower() in {"auto", "live"} else 1.0
    derived = (
        PORTFOLIO_SNAPSHOT_BASE_WORK_SECONDS
        + (quote_timeout * quote_passes)
        + PORTFOLIO_SNAPSHOT_COMPLETION_MARGIN_SECONDS
    )
    if derived > PORTFOLIO_SNAPSHOT_WORKER_TIMEOUT_CAP_SECONDS:
        raise ValueError(
            f"Portfolio quote timeout {quote_timeout:.1f}s cannot fit the "
            f"{PORTFOLIO_SNAPSHOT_WORKER_TIMEOUT_CAP_SECONDS:.1f}s IB worker budget."
        )
    return derived


@dataclass
class IBErrorRecord:
    timestamp: datetime
    req_id: int
    code: int
    message: str
    contract_symbol: str | None = None


@dataclass
class PortfolioPositionsResult:
    success: bool
    positions_with_contracts: List[Tuple[PositionItem, Contract]] = field(default_factory=list)
    error: str | None = None
    logs: List[str] = field(default_factory=list)
    ib_errors: List[IBErrorRecord] = field(default_factory=list)


class IBKRClient:
    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        account: str | None = None,
        mock: bool = False,
        mock_service: MockDataService | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.account = account
        self.mock = mock
        self.mock_service = mock_service or MockDataService()
        self._runner: IBThreadRunner | None = None
        if not self.mock:
            self._runner = IBThreadRunner()
            if self._runner.ib is None:
                raise RuntimeError("Failed to initialize IB thread")
            self.ib = self._runner.ib
        else:
            self.ib = IB()
        self._events_registered = False
        self._error_lock = threading.Lock()
        self._errors: List[str] = []
        self._error_records_lock = threading.Lock()
        self._error_records: List[IBErrorRecord] = []
        self._warnings_lock = threading.Lock()
        self._warnings: List[str] = []
        self._connected_lock = threading.Lock()
        self._connected_state = True if self.mock else False
        self._account_ready_event = threading.Event()
        self._positions_ready_event = threading.Event()
        self._req_seq_lock = threading.Lock()
        self._req_seq = 0
        self._last_contracts: List[Contract] = []
        self._account_summary_cache: Dict[str, str] = {}
        self._account_summary_ts: datetime | None = None
        self._account_updates_ready = False
        self._account_updates_lock = threading.Lock()
        self._account_updates_ts: datetime | None = None
        self._managed_accounts: List[str] = []
        self.active_account: str | None = None
        self._readonly_requested = True
        self.market_data_mode = self._normalize_market_data_mode(os.getenv("IB_MARKET_DATA_MODE", "delayed"))
        self._skip_quotes = False
        self._warned_live_entitlement_missing = False

    def connect(self) -> bool:
        if self.mock:
            logger.info("Mock mode enabled: skipping IBKR connection")
            return True
        return bool(self._run_ib(self._connect_impl))

    def disconnect(self) -> None:
        if self.mock:
            return
        self._run_ib(self._disconnect_impl)

    def is_connected(self) -> bool:
        if self.mock:
            return True
        if self._runner is not None and self._runner.in_thread():
            return bool(self.ib.isConnected())
        with self._connected_lock:
            return bool(self._connected_state)

    def account_subscription_usable(self) -> bool:
        """Report readiness without exposing the selected broker account identifier."""
        if self.mock:
            return True
        return bool(
            self.is_connected()
            and self.active_account
            and self._account_updates_ready
        )

    @property
    def ib_runner(self) -> IBThreadRunner | None:
        return self._runner

    def shutdown(self) -> None:
        if self.mock:
            return
        try:
            self._run_ib(self._disconnect_impl)
        except Exception:
            pass
        if self._runner is not None:
            self._runner.stop()

    def _run_ib(self, fn, *args, timeout: float | None = None, **kwargs):
        if self.mock or self._runner is None:
            return fn(*args, **kwargs)
        return self._runner.run(fn, *args, timeout=timeout, **kwargs)

    def _next_request_tag(self, prefix: str) -> str:
        with self._req_seq_lock:
            self._req_seq += 1
            seq = self._req_seq
        return f"{prefix}#{seq}"

    @staticmethod
    def _normalize_market_data_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"delayed", "live", "auto"}:
            return mode
        return "delayed"

    def set_market_data_mode(self, value: str | None) -> None:
        self.market_data_mode = self._normalize_market_data_mode(value)
        if self.market_data_mode != "live":
            self._skip_quotes = False
        self._warned_live_entitlement_missing = False

    def _debug_log(self, message: str) -> None:
        logger.info("IBKR %s", message)

    def _add_warning(self, message: str) -> None:
        with self._warnings_lock:
            self._warnings.append(message)

    def drain_warnings(self) -> List[str]:
        with self._warnings_lock:
            warnings = list(self._warnings)
            self._warnings.clear()
        return warnings

    def get_error_records(self, limit: int = 50) -> List[IBErrorRecord]:
        with self._error_records_lock:
            return list(self._error_records[-limit:])

    def format_error_records(self, limit: int = 50) -> List[str]:
        records = self.get_error_records(limit)
        lines: List[str] = []
        for record in records:
            ts = record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            contract = f" symbol={record.contract_symbol}" if record.contract_symbol else ""
            lines.append(f"[{ts}] reqId={record.req_id} code={record.code}{contract} {record.message}")
        return lines

    def drain_errors(self) -> List[str]:
        with self._error_lock:
            errors = list(self._errors)
            self._errors.clear()
        return list(dict.fromkeys(errors))

    def _register_events(self) -> None:
        if self._events_registered:
            return
        try:
            self.ib.errorEvent += self._on_ib_error
            self.ib.disconnectedEvent += self._on_ib_disconnected
            self.ib.connectedEvent += self._on_ib_connected
            self.ib.accountValueEvent += self._on_account_value
            self.ib.updatePortfolioEvent += self._on_update_portfolio
            self.ib.positionEvent += self._on_position
            self._events_registered = True
        except Exception:
            pass

    def _on_ib_connected(self) -> None:
        self._set_connected_state(True)

    def _on_ib_disconnected(self) -> None:
        self._set_connected_state(False)
        self._account_ready_event.clear()
        self._positions_ready_event.clear()
        with self._error_lock:
            self._errors.append("IBKR connection lost")

    def _on_account_value(self, _value) -> None:
        if not self._account_ready_event.is_set():
            self._debug_log("callback accountValueEvent received")
        self._account_ready_event.set()

    def _on_update_portfolio(self, _item) -> None:
        if not self._positions_ready_event.is_set():
            self._debug_log("callback updatePortfolioEvent received")
        self._account_ready_event.set()
        self._positions_ready_event.set()

    def _on_position(self, _position) -> None:
        if not self._positions_ready_event.is_set():
            self._debug_log("callback positionEvent received")
        self._positions_ready_event.set()

    def _on_ib_error(self, req_id: int, error_code: int, error_msg: str, contract) -> None:
        contract_symbol = self._contract_warning_symbol(contract)
        record = IBErrorRecord(
            timestamp=datetime.utcnow(),
            req_id=req_id,
            code=error_code,
            message=error_msg,
            contract_symbol=contract_symbol,
        )
        with self._error_records_lock:
            self._error_records.append(record)
            if len(self._error_records) > 200:
                self._error_records = self._error_records[-200:]
        if error_code == 10089:
            if not self._warned_live_entitlement_missing:
                self._add_warning("Live market data subscription missing; using delayed data when available")
                self._warned_live_entitlement_missing = True
            self._skip_quotes = self.market_data_mode == "live"
            return
        noisy_codes = {2104, 2106, 2158, 300, 322}
        if error_code in noisy_codes:
            return
        if error_code == 200:
            message = (
                f"{contract_symbol}: IBKR could not resolve the security definition."
                if contract_symbol
                else "IBKR could not resolve a security definition for an unattributed request."
            )
        elif error_code in {354, 10167, 10168}:
            message = f"{contract_symbol + ': ' if contract_symbol else ''}Market data unavailable: {error_msg}"
        elif error_code in {162, 366}:
            message = f"{contract_symbol + ': ' if contract_symbol else ''}Historical data request warning: {error_msg}"
        elif error_code in {1100, 1101, 1102}:
            message = f"IBKR connection warning: {error_msg}"
        else:
            message = f"{contract_symbol + ': ' if contract_symbol else ''}IBKR request failed: {error_msg}"
        with self._error_lock:
            self._errors.append(message)

    @staticmethod
    def _contract_warning_symbol(contract) -> str | None:
        if contract is None:
            return None
        for attribute in ("localSymbol", "symbol"):
            value = str(getattr(contract, attribute, "") or "").strip().upper()
            if value:
                return value
        return None

    def _connect_impl(self) -> bool:
        self._ensure_event_loop()
        self._debug_log(
            f"connect host={self.host} port={self.port} clientId={self.client_id} readonly_pref={self._readonly_requested}"
        )
        with self._error_lock:
            self._errors.clear()
        with self._warnings_lock:
            self._warnings.clear()
        self._account_updates_ready = False
        self._account_updates_ts = None
        self.active_account = None
        self._managed_accounts = []
        self._skip_quotes = False
        self._warned_live_entitlement_missing = False
        self._account_ready_event.clear()
        self._positions_ready_event.clear()
        try:
            try:
                self.ib.connect(
                    self.host, self.port, clientId=self.client_id, timeout=5, readonly=True
                )
                self._readonly_requested = True
            except TypeError:
                self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=5)
                self._readonly_requested = False
            self._register_events()
            connected = bool(self.ib.isConnected())
            self._set_connected_state(connected)
            if not connected:
                self._debug_log("connect failed: not connected after connect() call")
                return False
            warnings = self._ensure_account_subscription()
            for warning in warnings:
                self._add_warning(warning)
            self._debug_log(
                "connect ok "
                f"account={self._redact_account(self.active_account)} "
                f"managed={len(self._managed_accounts)}"
            )
            return True
        except Exception as exc:
            self._set_connected_state(False)
            logger.error("IBKR connect failed: %s", exc)
            return False

    def _disconnect_impl(self) -> None:
        self._ensure_event_loop()
        self._debug_log("disconnect requested")
        if self.ib.isConnected():
            if self.active_account:
                self._cancel_account_updates(self.active_account)
            self.ib.disconnect()
        self._set_connected_state(False)
        self._last_contracts = []
        self._account_updates_ready = False
        self._account_updates_ts = None
        self.active_account = None
        self._managed_accounts = []

    def _set_connected_state(self, value: bool) -> None:
        with self._connected_lock:
            self._connected_state = value
        if value:
            return
        self._account_ready_event.clear()
        self._positions_ready_event.clear()

    @staticmethod
    def _normalize_accounts(raw_accounts) -> List[str]:
        if raw_accounts is None:
            return []
        if isinstance(raw_accounts, str):
            return [acct.strip() for acct in raw_accounts.split(",") if acct.strip()]
        try:
            return [str(acct).strip() for acct in list(raw_accounts) if str(acct).strip()]
        except Exception:
            return []

    def _fetch_managed_accounts(self, timeout_seconds: float = 2.0) -> List[str]:
        if self.ib is None or not self.ib.isConnected():
            return []
        start = time.time()
        accounts: List[str] = []
        while time.time() - start < timeout_seconds:
            try:
                accounts = self._normalize_accounts(self.ib.managedAccounts())
            except Exception:
                accounts = []
            if accounts:
                break
            self.ib.sleep(0.1)
        return accounts

    def _resolve_active_account(self, managed_accounts: List[str]) -> Tuple[Optional[str], List[str]]:
        warnings: List[str] = []
        configured = (self.account or "").strip() or None
        active = None
        if configured:
            if configured in managed_accounts:
                active = configured
            else:
                warnings.append(
                    "Configured IB_ACCOUNT did not match a managed account; "
                    "using the first available managed account when possible."
                )
                if managed_accounts:
                    active = managed_accounts[0]
        else:
            if managed_accounts:
                active = managed_accounts[0]
        return active, warnings

    def _port_account_warning(self, account: Optional[str]) -> Optional[str]:
        if not account:
            return None
        acct = str(account).upper()
        if self.port == 7497 and not acct.startswith("DU"):
            return "Port 7497 is typically paper; active account does not look like a paper account"
        if self.port == 7496 and acct.startswith("DU"):
            return "Port 7496 is typically live; active account looks like a paper account"
        return None

    def _request_account_updates(
        self, account: str, subscribe: bool = True, timeout_seconds: float = 4.0, request_tag: str | None = None
    ) -> bool:
        tag = request_tag or self._next_request_tag("reqAccountUpdates")
        self._debug_log(
            f"{tag} account={self._redact_account(account)} subscribe={subscribe}"
        )
        if not subscribe:
            self._cancel_account_updates(account)
            return True
        self._account_ready_event.clear()
        try:
            client = getattr(self.ib, "client", None)
            if client is not None and hasattr(client, "reqAccountUpdates"):
                client.reqAccountUpdates(True, account)
            else:
                self.ib.reqAccountUpdates(account)
            if self._wait_for_account_ready(timeout_seconds):
                self._debug_log(f"{tag} account cache ready")
                return True
            if self._has_account_or_position_cache(account):
                self._debug_log(f"{tag} account cache present despite missing end callback")
                self._account_ready_event.set()
                return True
            self._debug_log(f"{tag} account cache still empty after {timeout_seconds:.2f}s")
            return False
        except TypeError:
            try:
                self.ib.reqAccountUpdates(account)
                if self._wait_for_account_ready(timeout_seconds):
                    return True
                return self._has_account_or_position_cache(account)
            except Exception as exc:
                logger.error("Account updates request failed: %s", exc)
                return False
        except Exception as exc:
            logger.error("Account updates request failed: %s", exc)
            return False

    def _has_account_or_position_cache(self, account: str | None = None) -> bool:
        account_filter = (account or self.active_account or "").strip()
        try:
            values = list(self.ib.accountValues(account_filter))
        except TypeError:
            values = list(self.ib.accountValues())
        except Exception:
            values = []
        if values:
            return True
        try:
            portfolio = list(self.ib.portfolio(account_filter))
        except TypeError:
            portfolio = list(self.ib.portfolio())
        except Exception:
            portfolio = []
        if portfolio:
            return True
        try:
            positions = list(self.ib.positions(account_filter))
        except TypeError:
            positions = list(self.ib.positions())
        except Exception:
            positions = []
        return bool(positions)

    def _cancel_account_updates(self, account: str) -> None:
        try:
            self.ib.reqAccountUpdates(False, account)
            return
        except TypeError:
            pass
        except Exception:
            return
        try:
            cancel_fn = getattr(self.ib, "cancelAccountUpdates", None)
            if callable(cancel_fn):
                cancel_fn()
        except Exception:
            pass

    def _request_account_summary(self, tags: str) -> Optional[int]:
        try:
            self.ib.reqAccountSummary("All", tags)
            return None
        except TypeError:
            try:
                req_id = self.ib.client.getReqId()
            except Exception:
                req_id = 9001
            try:
                self.ib.reqAccountSummary(req_id, "All", tags)
                return int(req_id)
            except Exception as exc:
                logger.error("Account summary request failed: %s", exc)
                return None
        except Exception as exc:
            logger.error("Account summary request failed: %s", exc)
            return None

    def _cancel_account_summary(self, req_id: Optional[int]) -> None:
        try:
            cancel_fn = getattr(self.ib, "cancelAccountSummary", None)
            if callable(cancel_fn):
                if req_id is None:
                    cancel_fn()
                else:
                    cancel_fn(req_id)
        except Exception:
            pass

    def _request_positions(self, timeout_seconds: float = 4.0, request_tag: str | None = None) -> List:
        tag = request_tag or self._next_request_tag("reqPositions")
        self._debug_log(f"{tag} requested")
        try:
            req_async = getattr(self.ib, "reqPositionsAsync", None)
            if callable(req_async):
                future = req_async()
                if not self._wait_for_future(future, timeout_seconds, f"{tag} completion"):
                    self._debug_log(f"{tag} timeout after {timeout_seconds:.2f}s")
                    return []
                result = future.result() if future.done() else []
                return list(result or [])
            result = self.ib.reqPositions()
            return list(result or [])
        except Exception as exc:
            logger.error("Positions request failed: %s", exc)
            return []

    def _ensure_account_subscription(self) -> List[str]:
        warnings: List[str] = []
        if self.ib is None or not self.ib.isConnected():
            warnings.append("IBKR not connected; cannot request account updates")
            return warnings
        if self._account_updates_ready and self.active_account:
            return warnings
        managed = self._fetch_managed_accounts()
        self._managed_accounts = managed
        if not managed:
            warnings.append("No managed accounts returned; cannot request account data")
            return warnings
        active, resolve_warnings = self._resolve_active_account(managed)
        warnings.extend(resolve_warnings)
        self.active_account = active
        if not active:
            warnings.append("Active account unresolved; cannot request account updates")
            return warnings
        request_tag = self._next_request_tag("account-subscribe")
        if self._request_account_updates(active, True, timeout_seconds=4.0, request_tag=request_tag):
            self._account_updates_ready = True
            self._account_updates_ts = datetime.utcnow()
            self._wait_for_account_ready(2.0, logs=None)
        else:
            if self._has_account_or_position_cache(active):
                self._account_updates_ready = True
                self._account_updates_ts = datetime.utcnow()
                self._account_ready_event.set()
                self._debug_log("account-subscribe cache detected; treating subscription as ready")
            else:
                warnings.append("Account updates subscription failed")
        return warnings

    def _account_summary_dict(self) -> Dict[str, str]:
        summary = {}
        items = []
        try:
            items = list(self.ib.accountValues())
        except Exception:
            items = []
        if not items:
            try:
                items = list(self.ib.accountSummary())
            except Exception:
                items = []
        for item in items:
            acct = getattr(item, "account", None)
            if self.active_account and acct and acct != self.active_account:
                continue
            key = f"{item.tag}:{item.currency}" if item.currency else item.tag
            summary[key] = item.value
        return summary

    def _get_portfolio_items(self) -> List[Tuple[PositionItem, Contract]]:
        items: List[Tuple[PositionItem, Contract]] = []
        raw_contracts: List[Contract] = []
        try:
            portfolio_items = list(self.ib.portfolio())
        except Exception:
            portfolio_items = []
        for p in portfolio_items:
            contract = self._normalize_contract(p.contract)
            items.append(
                (
                    PositionItem(
                        symbol=contract.symbol,
                        sec_type=contract.secType,
                        currency=contract.currency,
                        quantity=float(p.position),
                        avg_cost=float(p.averageCost) if p.averageCost is not None else None,
                        market_price=float(p.marketPrice) if p.marketPrice is not None else None,
                        market_value=float(p.marketValue) if p.marketValue is not None else None,
                        unrealized_pnl=float(p.unrealizedPNL) if p.unrealizedPNL is not None else None,
                        instrument_id=build_instrument_id(
                            provider="ibkr",
                            provider_id=str(contract.conId) if getattr(contract, "conId", None) else None,
                            symbol=contract.symbol,
                            sec_type=contract.secType,
                            exchange=contract.exchange,
                            primary_exchange=contract.primaryExchange,
                            currency=contract.currency,
                        ),
                        display_symbol=contract.symbol,
                        exchange=contract.exchange,
                        primary_exchange=contract.primaryExchange,
                        provider="ibkr",
                        provider_id=str(contract.conId) if getattr(contract, "conId", None) else None,
                    ),
                    contract,
                )
            )
            raw_contracts.append(contract)
        return self._apply_contract_qualification(items, raw_contracts)

    def _get_position_items_from_positions(self, positions) -> List[Tuple[PositionItem, Contract]]:
        items: List[Tuple[PositionItem, Contract]] = []
        raw_contracts: List[Contract] = []
        for p in positions:
            contract = self._normalize_contract(p.contract)
            items.append(
                (
                    PositionItem(
                        symbol=contract.symbol,
                        sec_type=contract.secType,
                        currency=contract.currency,
                        quantity=float(p.position),
                        avg_cost=float(getattr(p, "avgCost", None)) if getattr(p, "avgCost", None) is not None else None,
                        market_price=None,
                        market_value=None,
                        unrealized_pnl=None,
                        instrument_id=build_instrument_id(
                            provider="ibkr",
                            provider_id=str(contract.conId) if getattr(contract, "conId", None) else None,
                            symbol=contract.symbol,
                            sec_type=contract.secType,
                            exchange=contract.exchange,
                            primary_exchange=contract.primaryExchange,
                            currency=contract.currency,
                        ),
                        display_symbol=contract.symbol,
                        exchange=contract.exchange,
                        primary_exchange=contract.primaryExchange,
                        provider="ibkr",
                        provider_id=str(contract.conId) if getattr(contract, "conId", None) else None,
                    ),
                    contract,
                )
            )
            raw_contracts.append(contract)
        return self._apply_contract_qualification(items, raw_contracts)

    def _apply_contract_qualification(
        self, items: List[Tuple[PositionItem, Contract]], raw_contracts: List[Contract]
    ) -> List[Tuple[PositionItem, Contract]]:
        if not raw_contracts:
            return items
        qualified = self._qualify_contracts(raw_contracts)
        if qualified:
            qual_by_conid = {c.conId: c for c in qualified if c.conId}
            qual_by_key = {self._contract_key(c): c for c in qualified}
            updated: List[Tuple[PositionItem, Contract]] = []
            for pos, contract in items:
                replacement = None
                if contract.conId and contract.conId in qual_by_conid:
                    replacement = qual_by_conid[contract.conId]
                else:
                    replacement = qual_by_key.get(self._contract_key(contract))
                active_contract = replacement or contract
                pos.instrument_id = build_instrument_id(
                    provider="ibkr",
                    provider_id=str(active_contract.conId) if getattr(active_contract, "conId", None) else None,
                    symbol=active_contract.symbol,
                    sec_type=active_contract.secType,
                    exchange=active_contract.exchange,
                    primary_exchange=active_contract.primaryExchange,
                    currency=active_contract.currency,
                )
                pos.display_symbol = active_contract.symbol
                pos.exchange = active_contract.exchange
                pos.primary_exchange = active_contract.primaryExchange
                pos.provider = "ibkr"
                pos.provider_id = str(active_contract.conId) if getattr(active_contract, "conId", None) else None
                updated.append((pos, active_contract))
            items = updated
            self._last_contracts = [c for c in qualified]
        else:
            self._last_contracts = raw_contracts
        return items

    def fetch_snapshot(
        self,
        base_currency: str,
        fx: FXService,
        market_data: MarketDataService | None = None,
        quote_mode: str = "Snapshot",
        quote_timeout_seconds: float = 2.0,
    ) -> PortfolioSnapshot:
        quote_timeout_seconds = validate_portfolio_quote_timeout(quote_timeout_seconds)
        if not self.mock:
            # Primary warnings are scoped to this snapshot operation. Raw records remain
            # available in diagnostics across operations.
            self.drain_errors()
        snapshot = PortfolioSnapshot(
            timestamp=now_utc(),
            base_currency=base_currency,
            account_summary={},
            positions=[],
            warnings=[],
        )
        if self.mock:
            snapshot = self.mock_service.load_snapshot(base_currency)
        else:
            worker_timeout = derive_portfolio_snapshot_worker_timeout(
                quote_timeout_seconds,
                getattr(market_data, "market_data_mode", self.market_data_mode),
            )
            try:
                snapshot = self._run_ib(
                    self._fetch_snapshot_impl,
                    base_currency,
                    fx,
                    market_data,
                    quote_mode,
                    quote_timeout_seconds,
                    timeout=worker_timeout,
                )
            except IBTaskTimeoutError as exc:
                message = str(exc) or "IBKR request timed out"
                snapshot.warnings.append(message)
                if exc.still_finishing:
                    snapshot.warnings.append(
                        "IB worker state: still_finishing the timed-out portfolio snapshot; "
                        "follow-up broker requests will report busy until it completes."
                    )
            except IBThreadBusyError as exc:
                snapshot.warnings.append(str(exc))
            except TimeoutError as exc:
                message = str(exc) or "IBKR request timed out"
                snapshot.warnings.append(message)
            except Exception as exc:
                logger.exception("Snapshot fetch failed")
                detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                snapshot.warnings.append(f"Snapshot fetch failed: {detail}")

        try:
            self._compute_totals(snapshot, fx)
        except Exception as exc:
            logger.exception("Snapshot totals computation failed")
            detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            snapshot.warnings.append(f"Snapshot totals failed: {detail}")
        snapshot.warnings.extend(self.drain_warnings())
        snapshot.warnings.extend(self.drain_errors())
        snapshot.warnings = list(dict.fromkeys(snapshot.warnings))
        return snapshot

    def _fetch_snapshot_impl(
        self,
        base_currency: str,
        fx: FXService,
        market_data: MarketDataService | None = None,
        quote_mode: str = "Snapshot",
        quote_timeout_seconds: float = 2.0,
    ) -> PortfolioSnapshot:
        self._ensure_event_loop()
        if not self.ib.isConnected():
            return PortfolioSnapshot(
                timestamp=now_utc(),
                base_currency=base_currency,
                account_summary={},
                positions=[],
                warnings=["IBKR not connected"],
            )
        subscription_warnings = self._ensure_account_subscription()
        try:
            account_summary = self._snapshot_account_summary()
        except Exception as exc:
            account_summary = {}
            logger.error("Account summary fetch failed: %s", exc)
        try:
            positions_with_contracts = self._snapshot_positions()
        except Exception as exc:
            positions_with_contracts = []
            logger.error("Portfolio fetch failed: %s", exc)
        positions = [item for item, _ in positions_with_contracts]
        snapshot = PortfolioSnapshot(
            timestamp=now_utc(),
            base_currency=base_currency,
            account_summary=account_summary,
            positions=positions,
        )
        snapshot.warnings.extend(subscription_warnings)
        if not account_summary:
            snapshot.warnings.append("Account summary unavailable")
        if not positions:
            if account_summary:
                snapshot.warnings.append("No positions in account")
            else:
                snapshot.warnings.append("No positions returned from IBKR")

        if market_data is not None and quote_mode == "Snapshot":
            if self._skip_quotes:
                snapshot.warnings.append("Snapshot quotes skipped (missing market data subscription)")
                return snapshot
            try:
                contracts = [contract for _, contract in positions_with_contracts]
                quotes, quote_warnings = market_data.fetch_snapshot_quotes_batch(
                    contracts,
                    timeout_seconds=quote_timeout_seconds,
                    batch_size=max(1, len(contracts)),
                )
                snapshot.warnings.extend(quote_warnings)
                for pos, contract in positions_with_contracts:
                    key = market_data.quote_key(contract)
                    quote = quotes.get(key)
                    if quote is None or quote.price is None:
                        continue
                    pos.market_price = float(quote.price)
                    pos.market_value = float(quote.price) * pos.quantity
            except Exception as exc:
                logger.error("Snapshot quote fetch failed: %s", exc)
                snapshot.warnings.append(
                    "Snapshot quote fetch failed; account and position data were retained "
                    f"({type(exc).__name__})."
                )

        self._apply_unrealized_pnl_fallback(snapshot)
        return snapshot

    def _apply_unrealized_pnl_fallback(self, snapshot: PortfolioSnapshot) -> None:
        for pos in snapshot.positions:
            if pos.sec_type != "STK":
                continue
            if pos.unrealized_pnl is not None:
                continue
            if pos.avg_cost is None:
                continue
            if pos.market_price is not None:
                pos.unrealized_pnl = (pos.market_price - pos.avg_cost) * pos.quantity
                continue
            if pos.market_value is not None:
                pos.unrealized_pnl = pos.market_value - (pos.avg_cost * pos.quantity)

    def _snapshot_account_summary(self) -> Dict[str, str]:
        now = datetime.utcnow()
        if self._account_summary_ts and (now - self._account_summary_ts).total_seconds() < 2:
            return self._account_summary_cache or {}
        summary = self._account_summary_dict()
        if not summary:
            self._ensure_account_subscription()
            summary = self._account_summary_dict()
        if not summary:
            req_id = self._request_account_summary("NetLiquidation,TotalCashValue,AvailableFunds")
            self._wait_for_account_cache(1.0)
            summary = self._account_summary_dict()
            self._cancel_account_summary(req_id)
            if not summary:
                self._add_warning("Account summary still empty after account summary request")
        if summary:
            self._account_summary_cache = summary
            self._account_summary_ts = datetime.utcnow()
        return summary or self._account_summary_cache

    def _snapshot_positions(self) -> List[Tuple[PositionItem, Contract]]:
        result = self._get_portfolio_positions_impl(timeout_seconds=6.0)
        if not result.success:
            self._add_warning(result.error or "Portfolio positions request failed")
            for line in result.logs[-8:]:
                self._add_warning(f"[positions] {line}")
            for record in result.ib_errors[-5:]:
                ts = record.timestamp.strftime("%H:%M:%S")
                self._add_warning(
                    f"[positions][ib] {ts} reqId={record.req_id} code={record.code} {record.message}"
                )
        return result.positions_with_contracts

    def _compute_totals(self, snapshot: PortfolioSnapshot, fx: FXService) -> None:
        total_market = 0.0
        warnings: List[str] = []
        for pos in snapshot.positions:
            if pos.market_value is None:
                continue
            if pos.sec_type == "CASH" or pos.symbol.startswith("CASH"):
                continue
            currency = self._normalize_currency(pos.currency)
            if not self._is_valid_currency_code(currency):
                warnings.append(f"Invalid currency '{pos.currency}' for {pos.symbol}; skipping FX conversion")
                pos.base_market_value = None
                pos.fx_rate = None
                continue
            try:
                rate = fx.get_rate(snapshot.base_currency, currency)
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                warnings.append(f"FX lookup failed for {currency}->{snapshot.base_currency}: {detail}")
                pos.base_market_value = None
                pos.fx_rate = None
                continue
            if rate is None:
                if self.mock:
                    rate = 1.0
                    warnings.append(
                        f"FX unavailable for {currency}->{snapshot.base_currency}; using 1.0 (mock)"
                    )
                else:
                    warnings.append(f"FX unavailable for {currency}->{snapshot.base_currency}")
                    pos.base_market_value = None
                    pos.fx_rate = None
                    continue
            pos.fx_rate = rate
            pos.base_market_value = pos.market_value * rate
            total_market += pos.base_market_value
        snapshot.total_market_value = total_market if total_market > 0 else None

        nlv = self._summary_amount_in_base(
            snapshot.account_summary, "NetLiquidation", snapshot.base_currency, fx, warnings
        )
        snapshot.net_liquidation = nlv
        if nlv is None:
            warnings.append("Net liquidation unavailable")

        cash_by_currency = self._extract_cash_balances(snapshot.account_summary, snapshot.base_currency)
        cash_positions, total_cash, cash_warnings = self._build_cash_positions(
            cash_by_currency, snapshot.base_currency, fx
        )
        snapshot.total_cash = total_cash
        warnings.extend(cash_warnings)
        self._inject_cash_positions(snapshot, cash_positions)

        total_for_weights = 0.0
        if snapshot.total_market_value:
            total_for_weights += snapshot.total_market_value
        if snapshot.total_cash:
            total_for_weights += snapshot.total_cash

        if total_for_weights > 0:
            for pos in snapshot.positions:
                if pos.base_market_value is not None:
                    pos.weight = pos.base_market_value / total_for_weights

        self._compute_day_pnl_from_summary(snapshot, fx, warnings)
        snapshot.warnings.extend(warnings)

    def _compute_day_pnl_from_summary(
        self, snapshot: PortfolioSnapshot, fx: FXService, warnings: List[str]
    ) -> None:
        nlv = snapshot.net_liquidation
        prev = self._summary_amount_in_base(
            snapshot.account_summary,
            "PreviousDayEquityWithLoanValue",
            snapshot.base_currency,
            fx,
            warnings,
        )
        if nlv is not None and prev is not None:
            snapshot.day_pnl = float(nlv - prev)
            if prev != 0:
                snapshot.day_pnl_pct = float(snapshot.day_pnl / prev)
            snapshot.day_pnl_source = "account_summary"
            return

        for tag in ("DayPnL", "DailyPnL", "PnL"):
            value = self._summary_amount_in_base(
                snapshot.account_summary, tag, snapshot.base_currency, fx, warnings
            )
            if value is None:
                continue
            snapshot.day_pnl = float(value)
            if nlv is not None:
                previous_value = nlv - snapshot.day_pnl
                if previous_value != 0:
                    snapshot.day_pnl_pct = float(snapshot.day_pnl / previous_value)
            snapshot.day_pnl_source = "account_summary"
            return

    def _inject_cash_positions(self, snapshot: PortfolioSnapshot, cash_positions: List[PositionItem]) -> None:
        if not cash_positions:
            return
        snapshot.positions = [p for p in snapshot.positions if not p.symbol.startswith("CASH")]
        snapshot.positions = cash_positions + snapshot.positions

    @staticmethod
    def _normalize_currency(currency: str | None) -> str:
        return str(currency or "").strip().upper()

    @classmethod
    def _is_valid_currency_code(cls, currency: str | None) -> bool:
        value = cls._normalize_currency(currency)
        return len(value) == 3 and value.isalpha()

    def _extract_cash_balances(self, summary: Dict[str, str], base_currency: str) -> Dict[str, float]:
        base_ccy = self._normalize_currency(base_currency) or base_currency
        min_abs = 0.01
        cash: Dict[str, float] = {}
        aggregate_base: float | None = None

        def parse_amount(raw_value: str) -> float | None:
            try:
                amount = float(raw_value)
            except Exception:
                return None
            if abs(amount) < min_abs:
                return None
            return amount

        def add_cash(currency: str | None, amount: float | None) -> None:
            nonlocal aggregate_base
            if amount is None:
                return
            ccy = self._normalize_currency(currency)
            if not ccy or ccy == "BASE":
                aggregate_base = amount
                return
            if not self._is_valid_currency_code(ccy):
                return
            cash[ccy] = amount

        # Prefer native cash balances by currency when available.
        for key, value in summary.items():
            if key == "CashBalance":
                add_cash(base_ccy, parse_amount(value))
            if key.startswith("CashBalance:"):
                currency = key.split(":", 1)[1]
                add_cash(currency, parse_amount(value))
        if cash:
            return cash
        if aggregate_base is not None:
            return {base_ccy: aggregate_base}

        # Fallback to total cash values by currency.
        total_cash: Dict[str, float] = {}
        aggregate_total_base: float | None = None
        for key, value in summary.items():
            if key == "TotalCashValue":
                amount = parse_amount(value)
                if amount is not None:
                    aggregate_total_base = amount
            if key.startswith("TotalCashValue:"):
                currency = key.split(":", 1)[1]
                amount = parse_amount(value)
                ccy = self._normalize_currency(currency)
                if amount is None:
                    continue
                if not ccy or ccy == "BASE":
                    aggregate_total_base = amount
                    continue
                if not self._is_valid_currency_code(ccy):
                    continue
                total_cash[ccy] = amount
        if total_cash:
            return total_cash
        if aggregate_total_base is not None:
            return {base_ccy: aggregate_total_base}
        return {}

    def _build_cash_positions(
        self, cash_by_currency: Dict[str, float], base_currency: str, fx: FXService
    ) -> Tuple[List[PositionItem], Optional[float], List[str]]:
        if not cash_by_currency:
            return [], None, ["Cash balance unavailable"]
        warnings: List[str] = []
        base_ccy = self._normalize_currency(base_currency) or base_currency
        normalized_cash: Dict[str, float] = {}
        for currency, amount in cash_by_currency.items():
            ccy = self._normalize_currency(currency)
            if not ccy or ccy == "BASE":
                ccy = base_ccy
            if not self._is_valid_currency_code(ccy):
                warnings.append(f"Ignoring cash balance with invalid currency '{currency}'")
                continue
            normalized_cash[ccy] = normalized_cash.get(ccy, 0.0) + float(amount)
        if not normalized_cash:
            warnings.append("Cash balance unavailable")
            return [], None, warnings

        rates: Dict[str, Optional[float]] = {}
        all_convertible = True
        for currency, amount in normalized_cash.items():
            if abs(float(amount)) < 0.01:
                rates[currency] = 1.0 if currency == base_ccy else None
                continue
            try:
                rate = fx.get_rate(base_ccy, currency)
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                warnings.append(f"FX lookup failed for cash {currency}->{base_ccy}: {detail}")
                rate = None
            if rate is None and self.mock:
                rate = 1.0
                warnings.append(f"FX unavailable for cash {currency}->{base_ccy}; using 1.0 (mock)")
            rates[currency] = rate
            if rate is None:
                all_convertible = False
                warnings.append(f"FX unavailable for cash {currency}->{base_ccy}")

        prefer_aggregate_base = len(normalized_cash) == 1 and base_ccy in normalized_cash
        if all_convertible and prefer_aggregate_base:
            total_base = sum(amount * float(rates[currency]) for currency, amount in normalized_cash.items())
            cash_position = PositionItem(
                symbol="CASH",
                sec_type="CASH",
                currency=base_ccy,
                quantity=float(total_base),
                avg_cost=1.0,
                market_price=1.0,
                market_value=float(total_base),
                unrealized_pnl=0.0,
                base_market_value=float(total_base),
                fx_rate=1.0,
                instrument_id=build_instrument_id(
                    provider="ibkr",
                    symbol="CASH",
                    sec_type="CASH",
                    currency=base_ccy,
                ),
                display_symbol="CASH",
                provider="ibkr",
            )
            return [cash_position], float(total_base), warnings

        positions: List[PositionItem] = []
        total_cash = 0.0
        any_converted = False
        for currency, amount in sorted(normalized_cash.items()):
            rate = rates.get(currency)
            base_value = amount * rate if rate is not None else None
            if base_value is not None:
                total_cash += base_value
                any_converted = True
            symbol = "CASH" if currency == base_ccy and len(normalized_cash) == 1 else f"CASH_{currency}"
            positions.append(
                PositionItem(
                    symbol=symbol,
                    sec_type="CASH",
                    currency=currency,
                    quantity=float(amount),
                    avg_cost=1.0,
                    market_price=1.0,
                    market_value=float(amount),
                    unrealized_pnl=0.0,
                    base_market_value=float(base_value) if base_value is not None else None,
                    fx_rate=rate,
                    instrument_id=build_instrument_id(
                        provider="ibkr",
                        symbol=symbol,
                        sec_type="CASH",
                        currency=currency,
                    ),
                    display_symbol=symbol,
                    provider="ibkr",
                )
            )
        return positions, (total_cash if any_converted else None), warnings

    @classmethod
    def _account_base_currency(cls, summary: Dict[str, str]) -> Optional[str]:
        for tag in ("NetLiquidation", "EquityWithLoanValue", "TotalCashValue"):
            for key in summary:
                prefix, sep, suffix = key.partition(":")
                if not sep or prefix != tag:
                    continue
                ccy = cls._normalize_currency(suffix)
                if cls._is_valid_currency_code(ccy):
                    return ccy
        return None

    @classmethod
    def _summary_amount(
        cls, summary: Dict[str, str], tag: str, base_currency: str | None = None
    ) -> Tuple[Optional[float], Optional[str]]:
        """Return (value, currency) for an account summary tag.

        IB suffixes account-level tags with the *account's* base currency
        (e.g. ``NetLiquidation:EUR``), which may differ from the app base
        currency. A ``None`` currency means it could not be determined.
        """

        def parse(raw: str) -> Optional[float]:
            try:
                return float(raw)
            except Exception:
                return None

        base = cls._normalize_currency(base_currency) if base_currency else None
        if base:
            value = parse(summary.get(f"{tag}:{base}", ""))
            if value is not None:
                return value, base

        fallback: Tuple[Optional[float], Optional[str]] = (None, None)
        for key, raw in summary.items():
            prefix, sep, suffix = key.partition(":")
            if prefix != tag:
                continue
            value = parse(raw)
            if value is None:
                continue
            ccy = cls._normalize_currency(suffix) if sep else ""
            if cls._is_valid_currency_code(ccy):
                return value, ccy
            if fallback[0] is None and (not sep or ccy == "BASE"):
                fallback = (value, cls._account_base_currency(summary))
        return fallback

    def _summary_amount_in_base(
        self,
        summary: Dict[str, str],
        tag: str,
        base_currency: str,
        fx: FXService,
        warnings: List[str],
    ) -> Optional[float]:
        value, ccy = self._summary_amount(summary, tag, base_currency)
        if value is None:
            return None
        base = self._normalize_currency(base_currency)
        if ccy is None or ccy == base:
            return value
        try:
            rate = fx.get_rate(base, ccy)
        except Exception:
            rate = None
        if rate is None:
            warnings.append(f"FX unavailable for {ccy}->{base}; cannot convert {tag}")
            return None
        return value * float(rate)

    def get_contracts(self) -> List[Contract]:
        if self.mock:
            return []
        return list(self._run_ib(self._get_contracts_impl))

    def _get_contracts_impl(self) -> List[Contract]:
        self._ensure_event_loop()
        self._ensure_account_subscription()
        if self._last_contracts:
            return list(self._last_contracts)
        if not self.ib.isConnected():
            return []
        raw: List[Contract] = []
        try:
            positions = list(self.ib.positions())
        except Exception:
            positions = []
        if positions:
            raw = [self._normalize_contract(p.contract) for p in positions]
        else:
            try:
                raw = [self._normalize_contract(p.contract) for p in self.ib.portfolio()]
            except Exception:
                raw = []
        qualified = self._qualify_contracts(raw)
        self._last_contracts = qualified or raw
        return list(self._last_contracts)

    @staticmethod
    def _ensure_event_loop() -> None:
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

    def _wait_for_future(self, future, timeout_seconds: float, label: str) -> bool:
        deadline = time.time() + max(timeout_seconds, 0.1)
        while time.time() < deadline:
            if future.done():
                return True
            remaining = max(0.01, deadline - time.time())
            step = min(0.2, remaining)
            try:
                self.ib.waitOnUpdate(timeout=step)
            except Exception:
                try:
                    self.ib.sleep(step)
                except Exception:
                    time.sleep(step)
        self._debug_log(f"{label} timeout after {timeout_seconds:.2f}s")
        return bool(future.done())

    def _wait_for_account_ready(self, timeout_seconds: float, logs: List[str] | None = None) -> bool:
        if self._account_ready_event.is_set():
            return True
        deadline = time.time() + max(timeout_seconds, 0.1)
        while time.time() < deadline:
            try:
                if self.ib.accountValues() or self.ib.portfolio() or self.ib.positions():
                    self._account_ready_event.set()
                    return True
            except Exception:
                pass
            remaining = max(0.01, deadline - time.time())
            step = min(0.2, remaining)
            try:
                self.ib.waitOnUpdate(timeout=step)
            except Exception:
                try:
                    self.ib.sleep(step)
                except Exception:
                    time.sleep(step)
        if logs is not None:
            logs.append(self._stamp("Account-ready gate timed out"))
        return False

    def get_portfolio_positions(self, timeout_seconds: float = 6.0) -> PortfolioPositionsResult:
        if self.mock:
            snapshot = self.mock_service.load_snapshot("USD")
            items = [
                (
                    pos,
                    Contract(symbol=pos.symbol, secType=pos.sec_type, currency=pos.currency, exchange="SMART"),
                )
                for pos in snapshot.positions
                if not pos.symbol.startswith("CASH")
            ]
            return PortfolioPositionsResult(success=bool(items), positions_with_contracts=items)
        if not self.is_connected():
            return PortfolioPositionsResult(
                success=False,
                error="IBKR not connected",
                ib_errors=self.get_error_records(20),
            )
        try:
            return self._run_ib(
                self._get_portfolio_positions_impl,
                timeout_seconds,
                timeout=timeout_seconds + 2.0,
            )
        except TimeoutError:
            return PortfolioPositionsResult(
                success=False,
                error=f"Portfolio positions timed out after {timeout_seconds:.1f}s",
                logs=[self._stamp("Timeout waiting for IB thread while fetching positions")],
                ib_errors=self.get_error_records(20),
            )
        except Exception as exc:
            return PortfolioPositionsResult(
                success=False,
                error=f"Portfolio positions failed: {exc}",
                logs=[self._stamp(f"Exception in get_portfolio_positions: {exc}")],
                ib_errors=self.get_error_records(20),
            )

    def _get_portfolio_positions_impl(self, timeout_seconds: float = 6.0) -> PortfolioPositionsResult:
        logs: List[str] = []

        def log(message: str) -> None:
            stamped = self._stamp(message)
            logs.append(stamped)
            self._debug_log(message)

        if not self.ib.isConnected():
            log("Positions request aborted: disconnected")
            return PortfolioPositionsResult(
                success=False,
                error="IBKR not connected",
                logs=logs,
                ib_errors=self.get_error_records(20),
            )

        warnings = self._ensure_account_subscription()
        for warning in warnings:
            log(f"WARNING: {warning}")

        account_ready_timeout = min(2.5, max(0.8, timeout_seconds * 0.35))
        if self._wait_for_account_ready(account_ready_timeout):
            log(f"Account-ready gate satisfied in <= {account_ready_timeout:.1f}s")
        else:
            log(f"Account-ready gate timeout at {account_ready_timeout:.1f}s")

        try:
            cached_positions = list(self.ib.positions())
        except Exception:
            cached_positions = []
        if cached_positions:
            items = self._get_position_items_from_positions(cached_positions)
            log(f"Using cached positions: {len(items)} items")
            return PortfolioPositionsResult(success=bool(items), positions_with_contracts=items, logs=logs)

        cached_portfolio = self._get_portfolio_items()
        if cached_portfolio:
            log(f"Using cached portfolio items: {len(cached_portfolio)} items")
            return PortfolioPositionsResult(success=True, positions_with_contracts=cached_portfolio, logs=logs)

        deadline = time.time() + max(timeout_seconds, 1.0)
        attempt = 1
        while time.time() < deadline and attempt <= 3:
            remaining = max(0.2, deadline - time.time())
            req_timeout = min(2.5, remaining)
            req_tag = self._next_request_tag("reqPositions")
            self._positions_ready_event.clear()
            log(f"{req_tag} attempt={attempt} timeout={req_timeout:.1f}s")
            requested_positions = self._request_positions(timeout_seconds=req_timeout, request_tag=req_tag)
            if requested_positions:
                items = self._get_position_items_from_positions(requested_positions)
                if items:
                    log(f"{req_tag} received positions={len(items)}")
                    return PortfolioPositionsResult(success=True, positions_with_contracts=items, logs=logs)

            try:
                refreshed_positions = list(self.ib.positions())
            except Exception:
                refreshed_positions = []
            if refreshed_positions:
                items = self._get_position_items_from_positions(refreshed_positions)
                if items:
                    log(f"{req_tag} cache populated with positions={len(items)}")
                    return PortfolioPositionsResult(success=True, positions_with_contracts=items, logs=logs)

            refreshed_portfolio = self._get_portfolio_items()
            if refreshed_portfolio:
                log(f"{req_tag} fallback portfolio items={len(refreshed_portfolio)}")
                return PortfolioPositionsResult(success=True, positions_with_contracts=refreshed_portfolio, logs=logs)

            sleep_for = min(0.25, max(0.0, deadline - time.time()))
            if sleep_for > 0:
                try:
                    self.ib.sleep(sleep_for)
                except Exception:
                    time.sleep(sleep_for)
            attempt += 1

        error = (
            "No portfolio positions after reqPositions retries; "
            "connection alive but callbacks/cache remained empty"
        )
        log(error)
        return PortfolioPositionsResult(
            success=False,
            error=error,
            logs=logs,
            ib_errors=self.get_error_records(20),
        )

    def _wait_for_account_cache(self, timeout_seconds: float) -> None:
        if self.ib is None or not self.ib.isConnected():
            return
        self._wait_for_account_ready(timeout_seconds)

    def _ensure_account_updates(self) -> None:
        warnings = self._ensure_account_subscription()
        for warning in warnings:
            self._add_warning(warning)

    @staticmethod
    def _redact_account(account: Optional[str]) -> str:
        if not account:
            return "N/A"
        acct = str(account).strip()
        if len(acct) <= 4:
            return acct
        return f"{acct[:2]}****{acct[-2:]}"

    def _sample_account_values(self, limit: int = 3) -> List[str]:
        samples: List[str] = []
        items = []
        try:
            items = list(self.ib.accountValues())
        except Exception:
            items = []
        if not items:
            try:
                items = list(self.ib.accountSummary())
            except Exception:
                items = []
        for item in items[:limit]:
            currency = item.currency or ""
            key = f"{item.tag}:{currency}" if currency else item.tag
            acct = self._redact_account(getattr(item, "account", None))
            samples.append(f"{key}={item.value} acct={acct}")
        return samples

    def _sample_portfolio(self, limit: int = 3) -> List[str]:
        samples: List[str] = []
        try:
            items = list(self.ib.portfolio())
        except Exception:
            items = []
        for p in items[:limit]:
            contract = getattr(p, "contract", None)
            symbol = getattr(contract, "symbol", "N/A")
            sec_type = getattr(contract, "secType", "")
            qty = getattr(p, "position", None)
            mv = getattr(p, "marketValue", None)
            samples.append(f"{symbol} {sec_type} qty={qty} mv={mv}")
        return samples

    def _sample_positions(self, limit: int = 3) -> List[str]:
        samples: List[str] = []
        try:
            items = list(self.ib.positions())
        except Exception:
            items = []
        for p in items[:limit]:
            contract = getattr(p, "contract", None)
            symbol = getattr(contract, "symbol", "N/A")
            sec_type = getattr(contract, "secType", "")
            qty = getattr(p, "position", None)
            avg_cost = getattr(p, "avgCost", None)
            samples.append(f"{symbol} {sec_type} qty={qty} avgCost={avg_cost}")
        return samples

    def _sample_trades(self, limit: int = 3) -> List[str]:
        samples: List[str] = []
        try:
            items = list(self.ib.trades())
        except Exception:
            items = []
        for t in items[:limit]:
            contract = getattr(t, "contract", None)
            symbol = getattr(contract, "symbol", "N/A")
            action = getattr(getattr(t, "order", None), "action", "")
            status = getattr(getattr(t, "orderStatus", None), "status", "")
            samples.append(f"{symbol} {action} status={status}")
        return samples

    def _stamp(self, message: str) -> str:
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{ts}] {message}"

    def run_diagnostics(self) -> List[str]:
        if self.mock:
            return [self._stamp("Mock mode enabled: diagnostics skipped")]
        try:
            return list(self._run_ib(self._run_diagnostics_impl, timeout=25.0))
        except TimeoutError:
            return [self._stamp("Diagnostics timed out; IB thread unresponsive")]

    def _run_diagnostics_impl(self) -> List[str]:
        lines: List[str] = []

        def log(msg: str) -> None:
            lines.append(self._stamp(msg))

        log("Diagnostics started")
        log(f"Connected: {self.ib.isConnected()}")
        if self._runner is not None:
            log(
                f"IB thread id: {self._runner.thread_id}, current thread id: {threading.get_ident()}"
            )
        try:
            req_id = self.ib.client.getReqId()
        except Exception:
            req_id = "N/A"
        log(f"Client reqId: {req_id}")
        log(f"Read-only requested: {self._readonly_requested}")
        log(f"Skip snapshot quotes: {self._skip_quotes}")
        managed = self._fetch_managed_accounts()
        self._managed_accounts = managed
        log(f"Managed accounts available: {len(managed)}")
        log(f"Configured IB_ACCOUNT present: {bool((self.account or '').strip())}")
        active, resolve_warnings = self._resolve_active_account(managed)
        for warning in resolve_warnings:
            log(f"WARNING: {warning}")
        self.active_account = active
        log(f"Active account available: {active is not None}")
        port_warning = self._port_account_warning(active)
        if port_warning:
            log(f"WARNING: {port_warning}")

        if active:
            if self._request_account_updates(active, True):
                self._account_updates_ready = True
                self._account_updates_ts = datetime.utcnow()
                log("Requested account updates (reqAccountUpdates)")
            else:
                log("WARNING: Account updates subscription failed")

        def cache_counts(label: str) -> None:
            try:
                account_values = len(self.ib.accountValues())
            except Exception:
                account_values = 0
            try:
                portfolio = len(self.ib.portfolio())
            except Exception:
                portfolio = 0
            try:
                positions = len(self.ib.positions())
            except Exception:
                positions = 0
            try:
                trades = len(self.ib.trades())
            except Exception:
                trades = 0
            log(
                f"Cache counts ({label}): accountValues={account_values} portfolio={portfolio} "
                f"positions={positions} trades={trades}"
            )
            if account_values:
                for sample in self._sample_account_values():
                    log(f"AccountValue: {sample}")
            if portfolio:
                for sample in self._sample_portfolio():
                    log(f"Portfolio: {sample}")
            if positions:
                for sample in self._sample_positions():
                    log(f"Position: {sample}")
            if trades:
                for sample in self._sample_trades():
                    log(f"Trade: {sample}")

        cache_counts("pre-subscribe")

        warnings = self._ensure_account_subscription()
        for warning in warnings:
            log(f"WARNING: {warning}")

        for delay in (0.5, 1.5, 3.0):
            try:
                self.ib.sleep(delay)
            except Exception:
                time.sleep(delay)
            cache_counts(f"after {delay:.1f}s")

        log("Diagnostics completed")
        return lines

    def force_account_subscribe(self) -> List[str]:
        if self.mock:
            return [self._stamp("Mock mode enabled: account subscribe skipped")]
        try:
            return list(self._run_ib(self._force_account_subscribe_impl, timeout=12.0))
        except IBThreadBusyError as exc:
            return [self._stamp(str(exc))]
        except IBTaskTimeoutError as exc:
            if exc.still_finishing:
                return [
                    self._stamp(
                        "Force subscribe caller timed out; IB worker is still_finishing the subscribe operation"
                    )
                ]
            return [self._stamp("Force subscribe timed out before the queued task started; task cancelled")]
        except TimeoutError:
            return [self._stamp("Force subscribe timed out; IB thread unresponsive")]

    def _force_account_subscribe_impl(self) -> List[str]:
        lines: List[str] = []

        def log(msg: str) -> None:
            lines.append(self._stamp(msg))

        log("Force account subscribe started")
        if not self.ib.isConnected():
            log("ERROR: IBKR not connected")
            return lines

        managed = self._fetch_managed_accounts()
        self._managed_accounts = managed
        log(f"Managed accounts available: {len(managed)}")
        if not managed:
            log("WARNING: No managed accounts returned; cannot request account data")
            return lines

        active, resolve_warnings = self._resolve_active_account(managed)
        for warning in resolve_warnings:
            log(f"WARNING: {warning}")
        self.active_account = active
        log(f"Active account available: {active is not None}")
        port_warning = self._port_account_warning(active)
        if port_warning:
            log(f"WARNING: {port_warning}")
        if not active:
            log("ERROR: Active account unresolved; cannot request account updates")
            return lines

        if self._request_account_updates(active, True):
            self._account_updates_ready = True
            self._account_updates_ts = datetime.utcnow()
            log("Requested account updates (reqAccountUpdates)")
        else:
            log("WARNING: Account updates subscription failed")

        self._wait_for_account_cache(2.0)
        try:
            account_values = len(self.ib.accountValues())
        except Exception:
            account_values = 0
        try:
            portfolio_count = len(self.ib.portfolio())
        except Exception:
            portfolio_count = 0
        try:
            positions_count = len(self.ib.positions())
        except Exception:
            positions_count = 0
        log(
            f"Cache after account updates: accountValues={account_values} "
            f"portfolio={portfolio_count} positions={positions_count}"
        )

        if not self.ib.accountValues():
            log("Account values empty; requesting account summary")
            req_id = self._request_account_summary("NetLiquidation,TotalCashValue,AvailableFunds")
            self._wait_for_account_cache(2.0)
            self._cancel_account_summary(req_id)
            try:
                summary_count = len(self.ib.accountSummary())
            except Exception:
                summary_count = 0
            log(f"Account summary count: {summary_count}")

        if not self.ib.positions():
            log("Positions empty; requesting positions")
            requested = self._request_positions(timeout_seconds=3.0)
            if requested:
                self._wait_for_account_cache(2.0)
                log(f"reqPositions returned {len(requested)} items")
            log(f"Positions count: {len(self.ib.positions())}")

        try:
            final_account_values = len(self.ib.accountValues())
        except Exception:
            final_account_values = 0
        try:
            final_portfolio = len(self.ib.portfolio())
        except Exception:
            final_portfolio = 0
        try:
            final_positions = len(self.ib.positions())
        except Exception:
            final_positions = 0

        if final_account_values == 0 and final_positions == 0 and final_portfolio == 0:
            log(
                "WARNING: No account/portfolio data arrived. Check TWS API settings, "
                "read-only mode, paper vs live port, and account permissions."
            )

        if final_account_values:
            for sample in self._sample_account_values():
                log(f"AccountValue: {sample}")
        if final_portfolio:
            for sample in self._sample_portfolio():
                log(f"Portfolio: {sample}")
        if final_positions:
            for sample in self._sample_positions():
                log(f"Position: {sample}")

        log("Force account subscribe completed")
        return lines

    @staticmethod
    def _contract_key(contract: Contract) -> str:
        return f"{contract.symbol}:{contract.secType}:{contract.currency}"

    @staticmethod
    def _normalize_contract(contract: Contract) -> Contract:
        if contract.secType == "STK" and not contract.exchange:
            contract.exchange = "SMART"
        return contract

    def _qualify_contracts(self, contracts: List[Contract]) -> List[Contract]:
        if not contracts:
            return []
        try:
            qualified = self.ib.qualifyContracts(*contracts)
            return list(qualified) if qualified else []
        except Exception as exc:
            logger.error("Contract qualification failed: %s", exc)
            return contracts

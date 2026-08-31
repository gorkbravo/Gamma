from __future__ import annotations

import logging
import os
from dataclasses import replace
from hashlib import sha256
from typing import Any

from src.models.copilot import (
    COPILOT_MODEL_POLICY_VERSION,
    COPILOT_PROVIDER_STORAGE_POLICY_VERSION,
    CopilotDiagnostics,
    CopilotModelCapabilities,
    CopilotModelPolicyResolution,
    CopilotProfileCapabilityState,
    CopilotProviderStoragePolicy,
    CopilotResearchCardRequest,
    CopilotSafeProviderError,
)
from src.utils.time import now_utc


logger = logging.getLogger(__name__)

COPILOT_PRODUCT_PROFILES = ("auto", "quick", "standard", "deep")
SUPPORTED_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
OPENAI_BASELINE_MODEL = "gpt-5.6-luna"
CUSTOM_OPERATOR_PATH = "gamma_custom_loop"
AGENTS_SDK_PATH = "openai_agents_sdk"
RESPONSES_PATH = "responses_custom_loop"

_OPENAI_CAPABILITIES = CopilotModelCapabilities(
    structured_output=True,
    tool_use=True,
    streaming=True,
    reasoning=True,
    cancellation=True,
    provider_storage=True,
)
_MOCK_CAPABILITIES = CopilotModelCapabilities(
    structured_output=True,
    tool_use=True,
    streaming=True,
    reasoning=False,
    cancellation=True,
    provider_storage=False,
)
_CUSTOM_OPERATOR_CAPABILITIES = CopilotModelCapabilities(
    structured_output=True,
    tool_use=True,
    streaming=True,
    reasoning=False,
    cancellation=True,
    provider_storage=False,
)
_UNAVAILABLE_CAPABILITIES = CopilotModelCapabilities(
    structured_output=False,
    tool_use=False,
    streaming=False,
    reasoning=False,
    cancellation=False,
    provider_storage=False,
)

_SAFE_ERROR_COPY: dict[str, tuple[str, str, bool]] = {
    "disabled": (
        "Copilot is disabled by local configuration.",
        "Enable a supported Copilot provider in Settings or the Gamma environment.",
        False,
    ),
    "unconfigured": (
        "Copilot needs provider configuration.",
        "Configure the selected provider and restart Gamma, then retry.",
        False,
    ),
    "unavailable": (
        "The configured Copilot provider is currently unavailable.",
        "Check provider connectivity and retry. If the condition persists, inspect the diagnostic ID in local logs.",
        True,
    ),
    "rate_limited": (
        "The provider rate-limited this Copilot run.",
        "Wait briefly and retry, or reduce concurrent Copilot requests.",
        True,
    ),
    "quota_exhausted": (
        "The provider reported exhausted quota or spend capacity.",
        "Review provider quota and billing configuration before retrying.",
        False,
    ),
    "incompatible_model": (
        "The configured model does not satisfy this Copilot profile.",
        "Choose a supported profile/model combination or restore the Gamma baseline model.",
        False,
    ),
    "provider_error": (
        "The provider could not complete this Copilot run.",
        "Retry once. If it fails again, use the diagnostic ID to correlate with local logs.",
        True,
    ),
}


def _truthy(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def configured_provider_storage() -> CopilotProviderStoragePolicy:
    explicit = os.getenv("GAMMA_COPILOT_PROVIDER_STORAGE")
    if explicit is not None:
        requested_enabled = _truthy(explicit, True)
    else:
        # Compatibility with the established Checkpoint 1-5 setting. The
        # versioned setting above is the forward authority.
        requested_enabled = _truthy(os.getenv("GAMMA_COPILOT_STORE_RESPONSES"), True)
    requested = "enabled" if requested_enabled else "disabled"
    return CopilotProviderStoragePolicy(
        policy_version=COPILOT_PROVIDER_STORAGE_POLICY_VERSION,
        requested=requested,
        effective=requested,
        status="supported",
        reason=(
            "Provider response storage is enabled for response-id continuation; "
            "Gamma also persists its own local session record."
            if requested_enabled
            else "Provider response storage is disabled; Gamma reconstructs continuation from its local session record."
        ),
    )


class CopilotModelPolicy:
    """The single server-owned authority for Copilot product profile routing."""

    version = COPILOT_MODEL_POLICY_VERSION

    def __init__(
        self,
        provider: Any,
        *,
        configured_model: str | None = None,
        configured_reasoning_effort: str | None = None,
        provider_storage: CopilotProviderStoragePolicy | None = None,
        operator_orchestrator: str | None = None,
    ) -> None:
        self.provider = provider
        self.provider_name = str(getattr(provider, "provider_name", "unknown") or "unknown")
        self.configured_model = (
            str(configured_model or getattr(provider, "model", "") or OPENAI_BASELINE_MODEL).strip()
            or OPENAI_BASELINE_MODEL
        )
        self.configured_reasoning_effort = (
            str(configured_reasoning_effort or getattr(provider, "reasoning_effort", "medium") or "medium")
            .strip()
            .lower()
        )
        self.provider_storage = provider_storage or configured_provider_storage()
        self.operator_orchestrator = (
            str(
                operator_orchestrator
                if operator_orchestrator is not None
                else os.getenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "custom")
            )
            .strip()
            .lower()
        )

    @classmethod
    def from_environment(cls, provider: Any) -> "CopilotModelPolicy":
        storage = configured_provider_storage()
        if (
            os.getenv("GAMMA_COPILOT_PROVIDER_STORAGE") is None
            and os.getenv("GAMMA_COPILOT_STORE_RESPONSES") is None
            and hasattr(provider, "store_responses")
        ):
            enabled = bool(getattr(provider, "store_responses"))
            storage = replace(
                storage,
                requested="enabled" if enabled else "disabled",
                effective="enabled" if enabled else "disabled",
                reason=(
                    "Provider response storage is enabled for response-id continuation; Gamma also persists its own local session record."
                    if enabled
                    else "Provider response storage is disabled; Gamma reconstructs continuation from its local session record."
                ),
            )
        return cls(
            provider,
            configured_model=(
                os.getenv("GAMMA_COPILOT_MODEL")
                or getattr(provider, "model", None)
                or OPENAI_BASELINE_MODEL
            ),
            configured_reasoning_effort=(
                os.getenv("GAMMA_COPILOT_REASONING_EFFORT", "medium") or "medium"
            ),
            provider_storage=storage,
        )

    def resolve(
        self,
        request: CopilotResearchCardRequest,
        *,
        role: str | None = None,
    ) -> CopilotModelPolicyResolution:
        selected_profile, selection_source = self._selected_profile(request)
        resolved_profile = self._resolved_profile(selected_profile, request, role=role)
        orchestration_path = self._orchestration_path(role or request.role)
        custom_operator = orchestration_path == CUSTOM_OPERATOR_PATH
        adaptive_custom_operator = custom_operator and callable(
            getattr(self.provider, "stream_research_operator", None)
        )
        deterministic_custom_operator = custom_operator and not adaptive_custom_operator
        provider_state = (
            "configured" if deterministic_custom_operator else self.provider_state
        )
        provider = (
            "gamma_operator_executor"
            if deterministic_custom_operator
            else f"{self.provider_name}_operator"
            if adaptive_custom_operator
            else self.provider_name
        )
        model = (
            "gamma-operator-executor-v1"
            if deterministic_custom_operator
            else self._resolved_model(
                request,
                orchestration_path=orchestration_path,
            )
        )
        capabilities = (
            _CUSTOM_OPERATOR_CAPABILITIES
            if deterministic_custom_operator
            else self._capabilities(model)
        )
        effort = (
            None
            if deterministic_custom_operator
            else self._reasoning_effort(resolved_profile, request)
        )
        storage = (
            replace(
                self.provider_storage,
                effective="not_applicable",
                status="supported",
                reason=(
                    "The deterministic Gamma Operator makes no model-provider response "
                    "storage request; local session persistence remains active."
                ),
            )
            if deterministic_custom_operator
            else self._storage_for_capabilities(capabilities)
        )
        status = "ready"
        degradation_reason: str | None = None

        requested_provider = str(request.requested_provider or "").strip()
        if selected_profile not in COPILOT_PRODUCT_PROFILES:
            status = "unsupported"
            degradation_reason = (
                f"Product profile `{selected_profile}` is unsupported. "
                f"Supported profiles: {', '.join(COPILOT_PRODUCT_PROFILES)}."
            )
        elif requested_provider and requested_provider not in {provider, getattr(self.provider, "provider_id", None)}:
            status = "unsupported"
            degradation_reason = (
                f"Requested provider `{requested_provider}` is not the configured provider `{provider}`."
            )
        elif provider_state in {"disabled", "unconfigured", "unavailable"}:
            status = provider_state
            degradation_reason = self._provider_state_reason(provider_state)
        elif request.requested_model and not self._model_supported(str(request.requested_model)):
            status = "incompatible_model"
            degradation_reason = (
                f"Requested model `{request.requested_model}` is not in the configured Copilot model policy."
            )
        elif not all(
            (
                capabilities.structured_output,
                capabilities.tool_use,
                capabilities.streaming,
                capabilities.cancellation,
            )
        ):
            status = "incompatible_model"
            degradation_reason = "The resolved model lacks a required Copilot capability."
        elif storage.status != "supported":
            status = "degraded"
            degradation_reason = storage.reason
        elif orchestration_path == AGENTS_SDK_PATH and not capabilities.tool_use:
            status = "incompatible_model"
            degradation_reason = "The Agents SDK path requires model tool-use capability."

        routing_reason = self._routing_reason(
            selected_profile=selected_profile,
            resolved_profile=resolved_profile,
            provider=provider,
            model=model,
            effort=effort,
            orchestration_path=orchestration_path,
            status=status,
        )
        return CopilotModelPolicyResolution(
            policy_version=self.version,
            selected_profile=selected_profile,
            resolved_profile=resolved_profile,
            selection_source=selection_source,
            status=status,
            provider=provider,
            model=model,
            reasoning_mode="reasoning" if capabilities.reasoning else "unavailable",
            reasoning_effort=effort if capabilities.reasoning else None,
            orchestration_path=orchestration_path,
            capabilities=capabilities,
            routing_reason=routing_reason,
            provider_storage=storage,
            degradation_reason=degradation_reason,
        )

    @property
    def provider_state(self) -> str:
        provider = self.provider_name.lower()
        if provider == "disabled":
            return "disabled"
        if provider in {"unconfigured", "unknown"}:
            return "unconfigured"
        if provider in {"unavailable", "unavailable_copilot"}:
            return "unavailable"
        return "configured"

    def diagnostics(
        self,
        *,
        last_error: CopilotSafeProviderError | None = None,
    ) -> CopilotDiagnostics:
        profiles: list[CopilotProfileCapabilityState] = []
        for profile in COPILOT_PRODUCT_PROFILES:
            resolution = self.resolve(
                CopilotResearchCardRequest(domain="synthesis", selected_profile=profile)
            )
            profiles.append(
                CopilotProfileCapabilityState(
                    profile=profile,
                    status=resolution.status,
                    provider=resolution.provider,
                    model=resolution.model,
                    capabilities=resolution.capabilities,
                    guidance=resolution.degradation_reason,
                )
            )
        default_resolution = self.resolve(
            CopilotResearchCardRequest(
                domain="synthesis",
                selected_profile="auto",
                role="research_agent",
            )
        )
        operator_resolution = self.resolve(
            CopilotResearchCardRequest(
                domain="synthesis",
                selected_profile="auto",
                role="research_operator",
            ),
            role="research_operator",
        )
        return CopilotDiagnostics(
            provider_state=self.provider_state,
            provider=self.provider_name,
            provider_label=self._provider_label(),
            model_policy_version=self.version,
            profiles=profiles,
            default_resolution=default_resolution,
            operator_resolution=operator_resolution,
            local_storage=(
                "Gamma stores session prompts, structured results, context snapshots, evidence, "
                "warnings, safe diagnostics, and artifacts locally for replay."
            ),
            provider_storage=default_resolution.provider_storage,
            last_error=last_error,
        )

    def safe_error(
        self,
        *,
        category: str,
        run_id: str | None = None,
        model: str | None = None,
    ) -> CopilotSafeProviderError:
        normalized = category if category in _SAFE_ERROR_COPY else "provider_error"
        message, guidance, retryable = _SAFE_ERROR_COPY[normalized]
        seed = "|".join(
            (
                self.version,
                self.provider_name,
                model or self.configured_model,
                normalized,
                run_id or "configuration",
            )
        )
        diagnostic_id = f"cp6.{normalized}.{sha256(seed.encode('utf-8')).hexdigest()[:12]}"
        logger.warning(
            "Copilot provider diagnostic %s category=%s provider=%s model=%s",
            diagnostic_id,
            normalized,
            self.provider_name,
            model or self.configured_model,
        )
        return CopilotSafeProviderError(
            category=normalized,
            diagnostic_id=diagnostic_id,
            message=message,
            guidance=guidance,
            retryable=retryable,
            created_at=now_utc(),
        )

    def classify_error(
        self,
        value: str | Exception | None,
        *,
        run_id: str | None = None,
        model: str | None = None,
        fallback: str | None = None,
    ) -> CopilotSafeProviderError:
        text = str(value or "").lower()
        if fallback in _SAFE_ERROR_COPY:
            category = str(fallback)
        elif self.provider_state in {"disabled", "unconfigured", "unavailable"}:
            category = self.provider_state
        elif any(term in text for term in ("rate limit", "rate-limit", "429")):
            category = "rate_limited"
        elif any(term in text for term in ("quota", "billing", "insufficient_quota")):
            category = "quota_exhausted"
        elif any(term in text for term in ("model", "unsupported", "incompatible")):
            category = "incompatible_model"
        elif any(term in text for term in ("unreachable", "connection", "temporarily unavailable")):
            category = "unavailable"
        else:
            category = "provider_error"
        return self.safe_error(category=category, run_id=run_id, model=model)

    def with_effective_storage(
        self,
        resolution: CopilotModelPolicyResolution,
        *,
        supported: bool,
    ) -> CopilotModelPolicyResolution:
        if supported:
            return resolution
        requested = resolution.provider_storage.requested
        storage = replace(
            resolution.provider_storage,
            effective="unavailable",
            status="degraded",
            reason=(
                f"The configured provider cannot honor provider storage policy `{requested}`; "
                "Gamma local replay remains available."
            ),
        )
        return replace(
            resolution,
            status="degraded" if resolution.status == "ready" else resolution.status,
            provider_storage=storage,
            degradation_reason=storage.reason,
        )

    def _selected_profile(self, request: CopilotResearchCardRequest) -> tuple[str, str]:
        explicit = str(request.selected_profile or "").strip().lower()
        if explicit:
            if explicit in COPILOT_PRODUCT_PROFILES:
                return explicit, "user"
            return explicit, "user"
        effort = str(request.reasoning_effort or "").strip().lower()
        if effort in {"minimal", "low"}:
            return "quick", "legacy_reasoning_effort"
        if effort == "medium":
            return "standard", "legacy_reasoning_effort"
        if effort in {"high", "xhigh"}:
            return "deep", "legacy_reasoning_effort"
        return "auto", "default"

    @staticmethod
    def _resolved_profile(
        selected_profile: str,
        request: CopilotResearchCardRequest,
        *,
        role: str | None,
    ) -> str:
        if selected_profile not in COPILOT_PRODUCT_PROFILES:
            return selected_profile
        if selected_profile != "auto":
            return selected_profile
        normalized_role = str(role or request.role or "").lower()
        return "quick" if "operator" in normalized_role else "standard"

    def _resolved_model(
        self,
        request: CopilotResearchCardRequest,
        *,
        orchestration_path: str,
    ) -> str | None:
        requested = str(request.requested_model or "").strip()
        if requested:
            return requested
        if orchestration_path == AGENTS_SDK_PATH:
            return (
                str(
                    os.getenv("GAMMA_COPILOT_OPERATOR_AGENTS_MODEL")
                    or self.configured_model
                ).strip()
                or self.configured_model
            )
        if self.provider_name == "mock_copilot":
            return str(getattr(self.provider, "model", "") or "gamma-mock-research-card-v1")
        if self.provider_state != "configured":
            return None
        return self.configured_model

    def _reasoning_effort(
        self,
        resolved_profile: str,
        request: CopilotResearchCardRequest,
    ) -> str | None:
        legacy = str(request.reasoning_effort or "").strip().lower()
        if request.selected_profile is None and legacy in SUPPORTED_REASONING_EFFORTS:
            return legacy
        return {
            "quick": "low",
            "standard": "medium",
            "deep": "high",
        }.get(resolved_profile, self.configured_reasoning_effort)

    def _orchestration_path(self, role: str) -> str:
        if "operator" not in str(role or "").lower():
            return RESPONSES_PATH
        if self.operator_orchestrator in {"agents_sdk", "openai_agents_sdk"}:
            return AGENTS_SDK_PATH
        return CUSTOM_OPERATOR_PATH

    def _capabilities(self, model: str | None) -> CopilotModelCapabilities:
        if self.provider_state != "configured":
            return _UNAVAILABLE_CAPABILITIES
        if self.provider_name == "mock_copilot":
            return _MOCK_CAPABILITIES
        if self.provider_name in {"openai_responses", "openai_agents_sdk_operator"}:
            return _OPENAI_CAPABILITIES
        # Injected test providers and existing adapters are admitted with the
        # capabilities their current Copilot contract already exercises.
        if model == getattr(self.provider, "model", None) or self.provider_name not in {
            "disabled",
            "unconfigured",
            "unavailable",
        }:
            return CopilotModelCapabilities(
                structured_output=True,
                tool_use=True,
                streaming=True,
                reasoning=bool(getattr(self.provider, "reasoning_effort", None)),
                cancellation=True,
                provider_storage=hasattr(self.provider, "store_responses"),
            )
        return _UNAVAILABLE_CAPABILITIES

    def _storage_for_capabilities(
        self,
        capabilities: CopilotModelCapabilities,
    ) -> CopilotProviderStoragePolicy:
        requested = self.provider_storage.requested
        if self.provider_name == "mock_copilot":
            return replace(
                self.provider_storage,
                effective="not_applicable",
                status="supported",
                reason="Mock evidence never creates provider-retained response state; Gamma local storage still applies.",
            )
        if capabilities.provider_storage:
            return self.provider_storage
        return replace(
            self.provider_storage,
            effective="unavailable",
            status="degraded",
            reason=(
                f"The configured provider cannot honor provider storage policy `{requested}`; "
                "Gamma local replay remains available."
            ),
        )

    def _model_supported(self, model: str) -> bool:
        normalized = model.strip()
        if not normalized:
            return False
        if normalized == self.configured_model or normalized == getattr(self.provider, "model", None):
            return True
        return normalized in {
            "gpt-5.4",
            "gpt-5.5",
            "gpt-5.6",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
        }

    @staticmethod
    def _routing_reason(
        *,
        selected_profile: str,
        resolved_profile: str,
        provider: str,
        model: str | None,
        effort: str | None,
        orchestration_path: str,
        status: str,
    ) -> str:
        if status not in {"ready", "degraded"}:
            return (
                f"{selected_profile.title()} could not resolve on the configured provider "
                f"({status.replace('_', ' ')})."
            )
        profile_clause = (
            f"Auto selected {resolved_profile.title()}"
            if selected_profile == "auto"
            else f"{resolved_profile.title()} was user-selected"
        )
        return (
            f"{profile_clause}; routed to {provider}/{model or 'unavailable'} with "
            f"{effort or 'no'} reasoning through {orchestration_path.replace('_', ' ')}."
        )

    @staticmethod
    def _provider_state_reason(state: str) -> str:
        return {
            "disabled": "Copilot is disabled by configuration.",
            "unconfigured": "The selected Copilot provider is missing required configuration.",
            "unavailable": "The selected Copilot provider is unavailable.",
        }.get(state, "The configured Copilot provider cannot run this profile.")

    def _provider_label(self) -> str:
        return {
            "openai_responses": "OpenAI Responses",
            "mock_copilot": "Gamma deterministic mock",
            "disabled": "Disabled",
            "unconfigured": "OpenAI (configuration required)",
        }.get(self.provider_name, self.provider_name.replace("_", " ").title())

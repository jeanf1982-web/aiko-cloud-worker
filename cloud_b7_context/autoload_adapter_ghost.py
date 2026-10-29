"""GHOST-only composition seam for B7, never wired to production.

The trusted_history_provider MUST be supplied by the authenticated local AIKO
session implementation. This module cannot authenticate that provider itself.
No network, filesystem, persistent state, or secret processing.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Callable
from cloud_b7_context.guard_v4_ghost import ContextRejected, guarded_preprocess

def make_context_preprocessor(
    legacy_preprocessor: Callable,
    needs_history: Callable,
    trusted_history_provider: Callable,
):
    """Construct the boundary once, using trusted application-owned callbacks.

    The history returned here is not read from request context.
    To preserve plugin order, legacy_preprocessor is the entire existing chain.
    """
    if not all(callable(x) for x in
               (legacy_preprocessor, needs_history, trusted_history_provider)):
        raise ContextRejected("UNTRUSTED_ADAPTER_CONSTRUCTION")

    def preprocess(user_text, context):
        if type(user_text) is not str or type(context) is not dict:
            raise ContextRejected("INVALID_REQUEST_CONTEXT")
        required = needs_history(user_text)
        if type(required) is not bool:
            raise ContextRejected("INVALID_TRUSTED_ROUTING_DECISION")
        canonical_history = deepcopy(trusted_history_provider())
        if type(canonical_history) is not list:
            raise ContextRejected("INVALID_AUTHENTICATED_HISTORY")
        protected_context = dict(context)
        protected_context.pop("history", None)
        protected_context["history"] = canonical_history
        return guarded_preprocess(
            user_text, protected_context, legacy_preprocessor,
            requires_recent_context=required,
        )
    return preprocess

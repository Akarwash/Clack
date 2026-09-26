"""Clack: an acoustic side-channel security auditor.

Clack measures how vulnerable a keyboard environment is to microphone-based
keystroke inference, demonstrates the leakage live, applies an acoustic
countermeasure, and quantitatively verifies the reduction. The product is a
closed loop: AUDIT -> ATTACK SIMULATION -> DEFENSE -> VERIFY.

This package is organized so each module is owned by one component build plan
(see CLACK_BUILD_PLAN.md section 7). Importing :mod:`clack` must never require a
microphone, a model, or a network connection.
"""

__version__ = "0.1.0"

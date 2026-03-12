"""
Tool Call Validator — catches wrong-tool selections before they execute.

Strategy:
1. Define intent→tool mapping rules (regex patterns → expected tool names).
2. Before each tool runs, compare the selected tool against the user's intent.
3. If mismatch detected on a *mutating* tool, return a corrective error so
   the ReAct agent self-corrects in the next iteration instead of causing
   damage (e.g. creating an order when the user just wanted a search).
4. Read-only mismatches are logged but allowed through (low risk).
"""

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Intent rules ──────────────────────────────────────────
# Each rule maps a regex (matched against the latest user message,
# case-insensitive) to the set of tools that are *valid* for that intent.

@dataclass
class IntentRule:
    """A single intent-detection rule."""
    name: str                           # human-readable label
    pattern: re.Pattern                 # compiled regex
    expected_tools: set[str]            # tool names that make sense
    forbidden_tools: set[str] = field(  # tools that MUST NOT be called
        default_factory=set
    )


# Order of rules matters – first match wins.
INTENT_RULES: list[IntentRule] = [
    # ── ordering / buying ──
    IntentRule(
        name="create_new_order",
        pattern=re.compile(
            r"\b(book\s+it|order\s+it|buy\s+it|make\s+(an?\s+)?order|place\s+(an?\s+)?order|purchase)\b",
            re.IGNORECASE,
        ),
        expected_tools={"create_order", "find_books"},
        forbidden_tools={"add_to_order", "restock_book", "update_price"},
    ),
    IntentRule(
        name="add_to_existing_order",
        pattern=re.compile(
            r"\b(add\s+(it\s+|this\s+|that\s+|.*\s+)?to\s+order)\b",
            re.IGNORECASE,
        ),
        expected_tools={"add_to_order", "find_books"},
        forbidden_tools={"create_order"},
    ),
    # ── restock ──
    IntentRule(
        name="restock",
        pattern=re.compile(
            r"\b(restock|add\s+stock|replenish)\b",
            re.IGNORECASE,
        ),
        expected_tools={"restock_book", "find_books"},
        forbidden_tools={"create_order", "add_to_order", "update_price"},
    ),
    # ── price update ──
    IntentRule(
        name="update_price",
        pattern=re.compile(
            r"\b(update\s+price|change\s+price|set\s+price|new\s+price|price\s+to)\b",
            re.IGNORECASE,
        ),
        expected_tools={"update_price", "find_books"},
        forbidden_tools={"create_order", "add_to_order", "restock_book"},
    ),
    # ── search / lookup (read-only) ──
    IntentRule(
        name="search_books",
        pattern=re.compile(
            r"\b(find|search|look\s*up|show\s+me|what\s+books|do\s+you\s+have)\b",
            re.IGNORECASE,
        ),
        expected_tools={"find_books"},
        forbidden_tools={"create_order", "add_to_order", "restock_book", "update_price"},
    ),
    # ── order status ──
    IntentRule(
        name="order_status",
        pattern=re.compile(
            r"\b(order\s+status|status\s+of|check\s+order|where.s\s+my)\b",
            re.IGNORECASE,
        ),
        expected_tools={"order_status"},
        forbidden_tools={"create_order", "add_to_order"},
    ),
    # ── inventory ──
    IntentRule(
        name="inventory",
        pattern=re.compile(
            r"\b(inventory|stock\s+summary|low\s+stock|how\s+much\s+stock)\b",
            re.IGNORECASE,
        ),
        expected_tools={"inventory_summary"},
        forbidden_tools={"create_order", "add_to_order"},
    ),
    # ── list orders ──
    IntentRule(
        name="list_orders",
        pattern=re.compile(
            r"\b(list\s+orders|all\s+orders|show\s+orders)\b",
            re.IGNORECASE,
        ),
        expected_tools={"list_orders"},
        forbidden_tools={"create_order", "add_to_order"},
    ),
]

# Tools that modify the database — extra caution required.
MUTATING_TOOLS = {"create_order", "add_to_order", "restock_book", "update_price"}


# ── Validator ─────────────────────────────────────────────
class ToolCallValidator:
    """Validates tool selection against the user's detected intent."""

    def __init__(self, user_message: str):
        # Fix #8: guard against None
        self.user_message = user_message or ""
        self.matched_rules: list[IntentRule] = self._detect_all_intents()  # Fix #1
        self.matched_rule = self.matched_rules[0] if self.matched_rules else None

    # ── public API ────────────────────────────────────────
    def validate(self, tool_name: str) -> tuple[bool, str]:
        """Check if *tool_name* is appropriate for the current user intent.

        Returns
        -------
        (is_valid, reason)
            is_valid=True  → tool can proceed
            is_valid=False → tool should NOT run; *reason* explains why and
                             suggests the correct tool.
        """
        if not self.matched_rules:
            # No strong intent detected → allow anything.
            return True, ""

        all_forbidden = all(
            tool_name in rule.forbidden_tools
            for rule in self.matched_rules
        )
        if all_forbidden and tool_name in MUTATING_TOOLS:
            suggestion = ", ".join(
                sorted({t for r in self.matched_rules for t in r.expected_tools})
            )
            reason = (
                f"WRONG TOOL: Called '{tool_name}' but it is forbidden "
                f"for all detected intents: "
                f"{[r.name for r in self.matched_rules]}. "
                f"Use one of: {suggestion}."
            )
            logger.warning("Blocked mutating tool '%s'", tool_name)
            return False, reason

        return True, ""

    # ── private ───────────────────────────────────────────
    def _detect_all_intents(self) -> list[IntentRule]:
        """Fix #1: collect ALL matching rules instead of first match."""
        cleaned = re.sub(
            r"\b(don't|do not|cancel|stop|never|not)\s+", "", self.user_message, flags=re.IGNORECASE
        )
        return [rule for rule in INTENT_RULES if rule.pattern.search(cleaned)]

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ExpenseEntry(BaseModel):
    payer_name: str
    amount: Decimal
    description: Optional[str] = None


class ParticipantShare(BaseModel):
    participant_name: str
    paid_amount: Decimal
    fair_share: Decimal
    net_balance: Decimal
    status: str  # OVERPAID, UNDERPAID, EVEN


class SettlementTransfer(BaseModel):
    from_participant: str
    to_participant: str
    amount: Decimal
    currency: str = "USD"


class FinancialCalculationResult(BaseModel):
    total_expenses: Decimal
    currency: str
    split_method: str
    participant_shares: List[ParticipantShare]
    settlement_transfers: List[SettlementTransfer]
    discrepancy_cents: Decimal
    disclaimer: str = (
        "Calculations are based on reported chat expenses and proposed splits. "
        "They do not constitute confirmed debts, legal claims, or payment authorizations."
    )


class ExpenseCalculator:
    """Deterministic, penny-safe financial calculation engine for ACCORD."""

    CENT = Decimal("0.01")

    @classmethod
    def calculate_split(
        cls,
        expenses: List[ExpenseEntry],
        participants: List[str],
        split_method: str = "EQUAL",
        percentages: Optional[Dict[str, Decimal]] = None,
        custom_amounts: Optional[Dict[str, Decimal]] = None,
        weights: Optional[Dict[str, Decimal]] = None,
        currency: str = "USD",
    ) -> FinancialCalculationResult:
        """Compute penny-safe individual shares, net balances, and minimal settlement transfers."""
        if not participants:
            raise ValueError("At least one participant is required for calculation.")

        # Deduplicate participants while preserving order
        unique_participants = list(dict.fromkeys(p.strip() for p in participants if p and p.strip()))
        if not unique_participants:
            raise ValueError("Valid participant names required.")

        # Total reported expenses
        total_expenses = sum((e.amount for e in expenses), Decimal("0.00")).quantize(cls.CENT)

        # Aggregate total paid by each participant
        paid_map: Dict[str, Decimal] = {p: Decimal("0.00") for p in unique_participants}
        for exp in expenses:
            clean_payer = exp.payer_name.strip()
            # Match to known participant (case-insensitive fallback)
            matched = None
            for p in unique_participants:
                if p.lower() == clean_payer.lower():
                    matched = p
                    break
            if matched:
                paid_map[matched] += exp.amount.quantize(cls.CENT)
            else:
                # Add unknown payer if not in list
                paid_map[clean_payer] = exp.amount.quantize(cls.CENT)
                unique_participants.append(clean_payer)

        num_participants = len(unique_participants)

        # Calculate fair share per participant based on split method
        fair_share_map: Dict[str, Decimal] = {}

        if total_expenses == Decimal("0.00"):
            fair_share_map = {p: Decimal("0.00") for p in unique_participants}

        elif split_method.upper() == "EQUAL":
            # Penny-safe equal split: base share rounded down, remainder cents distributed
            base_share = (total_expenses / Decimal(num_participants)).quantize(cls.CENT, rounding=ROUND_DOWN)
            remainder = total_expenses - (base_share * Decimal(num_participants))
            remainder_cents = int((remainder * Decimal("100")).to_integral_value())

            for i, p in enumerate(unique_participants):
                extra = cls.CENT if i < remainder_cents else Decimal("0.00")
                fair_share_map[p] = base_share + extra

        elif split_method.upper() == "PERCENTAGE":
            if not percentages:
                raise ValueError("Percentages dictionary required for PERCENTAGE split method.")
            # Calculate raw shares
            running_sum = Decimal("0.00")
            for p in unique_participants:
                pct = percentages.get(p, Decimal("0.00"))
                share = (total_expenses * (pct / Decimal("100"))).quantize(cls.CENT, rounding=ROUND_HALF_UP)
                fair_share_map[p] = share
                running_sum += share

            # Adjust penny discrepancy on largest share
            diff = total_expenses - running_sum
            if diff != Decimal("0.00") and unique_participants:
                largest_p = max(unique_participants, key=lambda p: percentages.get(p, Decimal("0.00")))
                fair_share_map[largest_p] += diff

        elif split_method.upper() == "CUSTOM":
            if not custom_amounts:
                raise ValueError("Custom amounts dictionary required for CUSTOM split method.")
            running_sum = Decimal("0.00")
            for p in unique_participants:
                amt = custom_amounts.get(p, Decimal("0.00")).quantize(cls.CENT)
                fair_share_map[p] = amt
                running_sum += amt
            # Custom amounts might not equal total expenses if under-allocated
            # We keep specified custom amounts and record discrepancy

        elif split_method.upper() == "UNEQUAL":
            # Share based on integer/decimal weights (e.g. shares of rent)
            w_map = weights or {p: Decimal("1.0") for p in unique_participants}
            total_weight = sum((w_map.get(p, Decimal("1.0")) for p in unique_participants), Decimal("0.00"))
            if total_weight <= Decimal("0.00"):
                total_weight = Decimal(num_participants)

            running_sum = Decimal("0.00")
            for p in unique_participants:
                w = w_map.get(p, Decimal("1.0"))
                share = (total_expenses * (w / total_weight)).quantize(cls.CENT, rounding=ROUND_DOWN)
                fair_share_map[p] = share
                running_sum += share

            remainder = total_expenses - running_sum
            remainder_cents = int((remainder * Decimal("100")).to_integral_value())
            # Allocate remainder cents to highest weighted
            sorted_by_weight = sorted(unique_participants, key=lambda p: w_map.get(p, Decimal("1.0")), reverse=True)
            for i in range(min(remainder_cents, len(sorted_by_weight))):
                fair_share_map[sorted_by_weight[i]] += cls.CENT

        else:
            raise ValueError(f"Unsupported split method: {split_method}")

        # Build participant shares & net balances
        participant_shares: List[ParticipantShare] = []
        creditors: List[Dict[str, Any]] = []
        debtors: List[Dict[str, Any]] = []

        total_allocated = Decimal("0.00")
        for p in unique_participants:
            paid = paid_map.get(p, Decimal("0.00"))
            fair = fair_share_map.get(p, Decimal("0.00"))
            net = paid - fair
            total_allocated += fair

            if net > cls.CENT:
                status = "OVERPAID"
                creditors.append({"name": p, "balance": net})
            elif net < -cls.CENT:
                status = "UNDERPAID"
                debtors.append({"name": p, "balance": abs(net)})
            else:
                status = "EVEN"

            participant_shares.append(
                ParticipantShare(
                    participant_name=p,
                    paid_amount=paid,
                    fair_share=fair,
                    net_balance=net,
                    status=status,
                )
            )

        # Compute minimal settlement transfers using greedy algorithm
        settlement_transfers: List[SettlementTransfer] = []
        creditors.sort(key=lambda x: x["balance"], reverse=True)
        debtors.sort(key=lambda x: x["balance"], reverse=True)

        c_idx = 0
        d_idx = 0
        while c_idx < len(creditors) and d_idx < len(debtors):
            cred = creditors[c_idx]
            debt = debtors[d_idx]

            transfer_amt = min(cred["balance"], debt["balance"]).quantize(cls.CENT)
            if transfer_amt > Decimal("0.00"):
                settlement_transfers.append(
                    SettlementTransfer(
                        from_participant=debt["name"],
                        to_participant=cred["name"],
                        amount=transfer_amt,
                        currency=currency,
                    )
                )

            cred["balance"] -= transfer_amt
            debt["balance"] -= transfer_amt

            if cred["balance"] < cls.CENT:
                c_idx += 1
            if debt["balance"] < cls.CENT:
                d_idx += 1

        discrepancy = (total_expenses - total_allocated).quantize(cls.CENT)

        return FinancialCalculationResult(
            total_expenses=total_expenses,
            currency=currency,
            split_method=split_method,
            participant_shares=participant_shares,
            settlement_transfers=settlement_transfers,
            discrepancy_cents=discrepancy,
        )


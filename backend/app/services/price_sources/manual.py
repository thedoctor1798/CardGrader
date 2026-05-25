from sqlmodel import Session, select

from ...models import Card, PriceHistory
from .base import PriceData, PriceSource, PriceSourceResult


class ManualPriceSource(PriceSource):
    source_name = "manual"

    def fetch(
        self,
        session: Session,
        card: Card,
        owned_card_id: int | None = None,
    ) -> PriceSourceResult:
        latest = None
        if owned_card_id is not None:
            latest = session.exec(
                select(PriceHistory)
                .where(PriceHistory.card_id == card.id)
                .where(PriceHistory.owned_card_id == owned_card_id)
                .where(PriceHistory.source == self.source_name)
                .where(PriceHistory.error_code.is_(None))
                .order_by(PriceHistory.fetched_at.desc(), PriceHistory.id.desc())
            ).first()

        if latest is None:
            latest = session.exec(
                select(PriceHistory)
                .where(PriceHistory.card_id == card.id)
                .where(PriceHistory.source == self.source_name)
                .where(PriceHistory.error_code.is_(None))
                .order_by(PriceHistory.fetched_at.desc(), PriceHistory.id.desc())
            ).first()

        if latest is None:
            return PriceSourceResult(
                ok=False,
                source=self.source_name,
                card_id=card.id or 0,
                error="manual_price_missing",
                message="No manual price has been entered for this card.",
                debug_metadata={"provider": self.source_name},
            )

        return PriceSourceResult(
            ok=True,
            source=self.source_name,
            card_id=card.id or 0,
            source_card_id=latest.source_card_id,
            source_url=latest.source_url,
            prices=PriceData(
                raw_price=latest.raw_price,
                market_price=latest.market_price,
                low_price=latest.low_price,
                high_price=latest.high_price,
                psa_7=latest.psa_7,
                psa_8=latest.psa_8,
                psa_9=latest.psa_9,
                psa_10=latest.psa_10,
                currency=latest.currency,
            ),
            confidence=latest.confidence or "manual",
            condition_hint=latest.condition_hint,
            raw_response={"price_history_id": latest.id},
            debug_metadata={"provider": self.source_name, "source_price_history_id": latest.id},
        )

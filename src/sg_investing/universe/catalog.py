"""Load seed securities and maintain source-labelled universe membership."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from sg_investing.models import Security, UniverseMembership


class ConfiguredSecurity(BaseModel):
    model_config = ConfigDict(frozen=True)

    universe: str
    effective_from: date
    source: str
    security: Security


class UniverseCatalog(BaseModel):
    """A serializable catalog assembled from config and source adapters."""

    model_config = ConfigDict(frozen=True)

    history_start: date
    securities: list[ConfiguredSecurity] = Field(default_factory=list)

    def security_by_ticker(self, ticker: str) -> Security:
        matches = {entry.security.security_id: entry.security for entry in self.securities if entry.security.ticker == ticker.upper()}
        if len(matches) != 1:
            raise KeyError(f"Expected one configured security for ticker {ticker}, found {len(matches)}.")
        return next(iter(matches.values()))

    def memberships(self) -> list[UniverseMembership]:
        return [
            UniverseMembership(
                universe=entry.universe,
                security_id=entry.security.security_id,
                effective_from=entry.effective_from,
                source=entry.source,
            )
            for entry in self.securities
        ]

    def merge_current_listings(
        self,
        *,
        universe: str,
        source: str,
        as_of: date,
        listings: list[Security],
    ) -> "UniverseCatalog":
        """Return a new catalog with an auditable current-listing snapshot."""

        existing_by_key = {
            (entry.security.isin, entry.security.exchange, entry.security.ticker): entry.security
            for entry in self.securities
        }
        existing_memberships = {(entry.universe, entry.security.security_id) for entry in self.securities}
        additions: list[ConfiguredSecurity] = []
        for listing in listings:
            key = (listing.isin, listing.exchange, listing.ticker)
            security = existing_by_key.get(key, listing)
            if (universe, security.security_id) not in existing_memberships:
                additions.append(
                    ConfiguredSecurity(
                        universe=universe,
                        effective_from=as_of,
                        source=source,
                        security=security,
                    )
                )
                existing_memberships.add((universe, security.security_id))
                existing_by_key[key] = security
        return self.model_copy(update={"securities": [*self.securities, *additions]})


def load_catalog(path: str | Path) -> UniverseCatalog:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return UniverseCatalog.model_validate(payload)


def save_catalog(catalog: UniverseCatalog, path: str | Path) -> None:
    """Atomically persist a frontend-safe, auditable catalog snapshot."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(target)

from datetime import datetime, timezone
from sqlalchemy import BigInteger, Float, String, DateTime, Index, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class NodeMetric(Base):
    __tablename__ = "node_metrics"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    cpu_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    mem_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    swap_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    disk_read_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_write_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_used_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    net_in_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_out_bps: Mapped[float | None] = mapped_column(Float, nullable=True)

    load1: Mapped[float | None] = mapped_column(Float, nullable=True)
    load5: Mapped[float | None] = mapped_column(Float, nullable=True)
    load15: Mapped[float | None] = mapped_column(Float, nullable=True)

    temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)

    gpu_util_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_vram_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("idx_node_ts", "node_id", "ts"),
    )

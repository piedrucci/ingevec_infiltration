import uuid
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class DivisionManager(Base):
    __tablename__='division_manager'; __table_args__={'schema':'app'}
    id: Mapped[int] = mapped_column(Integer, primary_key=True); name: Mapped[str] = mapped_column(String(255), nullable=False)
class ProjectManager(Base):
    __tablename__='project_manager'; __table_args__={'schema':'app'}
    id: Mapped[int] = mapped_column(Integer, primary_key=True); division_manager_id: Mapped[int] = mapped_column(ForeignKey('app.division_manager.id'), nullable=False); name: Mapped[str] = mapped_column(String(255), nullable=False)
class ProjectAdmin(Base):
    __tablename__='project_admin'; __table_args__={'schema':'app'}
    id: Mapped[int] = mapped_column(Integer, primary_key=True); project_manager_id: Mapped[int] = mapped_column(ForeignKey('app.project_manager.id'), nullable=False); name: Mapped[str] = mapped_column(String(255), nullable=False)
def _catalog(clsname, tablename):
    return type(clsname, (Base,), {'__tablename__':tablename, '__table_args__':{'schema':'app'}, 'id':mapped_column(Integer, primary_key=True), 'name':mapped_column(String(255), nullable=False)})
Typology=_catalog('Typology','typology'); Location=_catalog('Location','location'); Supervisor=_catalog('Supervisor','supervisor'); Classification=_catalog('Classification','classification'); ItemType=_catalog('ItemType','item_type'); Subcontractor=_catalog('Subcontractor','subcontractor')
class ExcelImport(Base):
    __tablename__='excel_import'; __table_args__={'schema':'app'}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4); original_filename: Mapped[str] = mapped_column(String(255), nullable=False); file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False); status: Mapped[str] = mapped_column(String(32), nullable=False, default='RECEIVED'); source_sheet: Mapped[str] = mapped_column(String(128), nullable=False, default='Año 2026'); row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0); imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
class ExcelSourceRow(Base):
    __tablename__='excel_source_row'; __table_args__=(UniqueConstraint('excel_import_id','sheet_name','row_number'), {'schema':'app'})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4); excel_import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('app.excel_import.id', ondelete='CASCADE'), nullable=False); sheet_name: Mapped[str] = mapped_column(String(128), nullable=False); row_number: Mapped[int] = mapped_column(Integer, nullable=False); raw_cells: Mapped[dict] = mapped_column(JSONB, nullable=False); row_hash: Mapped[str] = mapped_column(String(64), nullable=False); normalization_status: Mapped[str] = mapped_column(String(32), nullable=False, default='PENDING'); normalization_error: Mapped[str | None] = mapped_column(Text)
class Project(Base):
    __tablename__='project'; __table_args__={'schema':'app'}
    id: Mapped[str] = mapped_column(String(100), primary_key=True); public_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, default=uuid.uuid4, server_default=func.gen_random_uuid(), nullable=False); name: Mapped[str] = mapped_column(String(255), nullable=False); typology_id: Mapped[int] = mapped_column(ForeignKey('app.typology.id'), nullable=False); location_id: Mapped[int] = mapped_column(ForeignKey('app.location.id'), nullable=False); municipal_reception_date: Mapped[date | None] = mapped_column(Date); supervisor_id: Mapped[int] = mapped_column(ForeignKey('app.supervisor.id'), nullable=False); project_admin_id: Mapped[int | None] = mapped_column(ForeignKey('app.project_admin.id'))
class PostventaItem(Base):
    __tablename__='postventa_item'; __table_args__={'schema':'app'}
    id: Mapped[int] = mapped_column(Integer, primary_key=True); public_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, default=uuid.uuid4, server_default=func.gen_random_uuid(), nullable=False); source_row_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('app.excel_source_row.id', ondelete='CASCADE'), unique=True); project_id: Mapped[str] = mapped_column(ForeignKey('app.project.id'), nullable=False); classification_id: Mapped[int] = mapped_column(ForeignKey('app.classification.id'), nullable=False); item_type_id: Mapped[int] = mapped_column(ForeignKey('app.item_type.id'), nullable=False); notes: Mapped[str] = mapped_column(Text, nullable=False); request_date: Mapped[date | None] = mapped_column(Date); subcontractor_id: Mapped[int | None] = mapped_column(ForeignKey('app.subcontractor.id')); handled_by: Mapped[str | None] = mapped_column(String(255))

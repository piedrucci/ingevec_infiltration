"""Run with SPLIT_TEST_DATABASE=1 and DATABASE_URL pointing to disposable split_test."""
import copy
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.commands.split_category_causes import execute_review, load_review
from app.db import Base, engine
from app.models import (FailureCause, FailureCauseCategory, FailureCauseCategoryLink,
                        PostventaItem, PostventaItemFailureCause)


@unittest.skipUnless(os.environ.get('SPLIT_TEST_DATABASE') == '1', 'Requires disposable PostgreSQL')
class SplitIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert engine.url.database == 'split_test', 'Never run these fixtures against business data'
        with engine.begin() as conn:
            conn.execute(text('CREATE EXTENSION IF NOT EXISTS pg_trgm'))
            conn.execute(text('CREATE SCHEMA IF NOT EXISTS app'))
            Base.metadata.create_all(conn)
            conn.execute(text('ALTER TABLE app.failure_cause_category_link DROP CONSTRAINT IF EXISTS uq_failure_cause_category_link_cause'))

    def setUp(self):
        self.conn = engine.connect()
        self.tx = self.conn.begin()
        self.db = Session(bind=self.conn)
        ids = {}
        for table in ('typology', 'location', 'supervisor'):
            ids[table] = self.conn.execute(text(f"INSERT INTO app.{table}(name) VALUES ('Test') RETURNING id")).scalar_one()
        self.conn.execute(text("INSERT INTO app.project(id,name,typology_id,location_id,supervisor_id) VALUES ('TEST','Test',:typology,:location,:supervisor)"), ids)
        classification = self.conn.execute(text("INSERT INTO app.classification(name) VALUES ('Test') RETURNING id")).scalar_one()
        item_type = self.conn.execute(text("INSERT INTO app.item_type(name) VALUES ('Test') RETURNING id")).scalar_one()
        self.a = FailureCauseCategory(code='A', display_name_es='Category A')
        self.b = FailureCauseCategory(code='B', display_name_es='Category B')
        self.old = FailureCause(code='SHARED', display_name_es='Shared')
        self.other = FailureCause(code='OTHER', display_name_es='Other')
        self.db.add_all([self.a,self.b,self.old,self.other]); self.db.flush()
        self.db.add_all([FailureCauseCategoryLink(failure_cause_id=self.old.id,category_id=c.id) for c in (self.a,self.b)])
        self.item = PostventaItem(project_id='TEST',notes='Original observation',classification_id=classification,item_type_id=item_type,failure_cause_id=self.old.id)
        self.db.add(self.item); self.db.flush()
        self.link = PostventaItemFailureCause(postventa_item_id=self.item.id,failure_cause_id=self.old.id,assignment_source='MANUAL',assigned_by='tester')
        self.db.add_all([self.link,PostventaItemFailureCause(postventa_item_id=self.item.id,failure_cause_id=self.other.id,assignment_source='MANUAL')]);self.db.flush()
        cats=[{'id':c.id,'code':c.code,'name':c.display_name_es} for c in (self.a,self.b)]
        self.data={'catalog':[{'id':self.old.id,'code':'SHARED','name':'Shared','categories':cats}], 'rows':[{
            'item_id':self.item.id,'item_public_id':str(self.item.public_id),'project_id':'TEST','project_name':'Test',
            'observation':self.item.notes,'current_cause_id':self.old.id,'current_cause_code':'SHARED','current_cause_name':'Shared',
            'available_categories':cats,'selected_category_codes':['A','B'],
            'all_current_causes':[{'id':c.id,'code':c.code,'name':c.display_name_es} for c in (self.old,self.other)],
            'assignment_source':'MANUAL','assigned_by':'tester','assigned_at':str(self.link.assigned_at),'source_document_id':None}]}

    def tearDown(self):
        self.db.close();self.tx.rollback();self.conn.close()

    def migration(self):
        spec=importlib.util.spec_from_file_location('split_migration','/app/migrations/versions/20261008_0023_single_category_per_cause.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.op=Operations(MigrationContext.configure(self.conn))
        return module

    def test_dry_run_no_mutation_then_apply_preserves_other_causes_and_provenance(self):
        summary=execute_review(self.db,self.data)
        self.assertEqual(summary['new_assignments'],2)
        self.assertTrue(self.old.is_active)
        self.assertIsNone(self.db.scalar(select(FailureCause).where(FailureCause.code=='SHARED__A')))
        stamp=self.link.assigned_at
        execute_review(self.db,self.data,apply=True)
        links=self.db.scalars(select(PostventaItemFailureCause).where(PostventaItemFailureCause.postventa_item_id==self.item.id)).all()
        self.assertEqual(len(links),3)
        self.assertIn(self.other.id,[l.failure_cause_id for l in links])
        for link in links:
            if link.failure_cause_id!=self.other.id:
                self.assertEqual((link.assignment_source,link.assigned_by,link.assigned_at),('MANUAL','tester',stamp))
        self.assertFalse(self.old.is_active)
        self.assertEqual(self.item.failure_cause_id,min(l.failure_cause_id for l in links))
        with self.assertRaisesRegex(ValueError,'already retired'):execute_review(self.db,self.data,apply=True)

    def test_stale_snapshot_blocks_apply(self):
        self.item.notes='Changed';self.db.flush()
        with self.assertRaisesRegex(ValueError,'snapshot changed'):execute_review(self.db,self.data,apply=True)
        self.assertTrue(self.old.is_active)

    def test_missing_coverage_blocks_apply(self):
        self.data['rows']=[]
        with self.assertRaisesRegex(ValueError,'coverage'):execute_review(self.db,self.data,apply=True)

    def test_review_rejects_missing_invalid_and_duplicate_selections(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'review.json'
            for codes in ([],['UNKNOWN'],['A','A'],[{'code':'A'}]):
                data=copy.deepcopy(self.data);data['rows'][0]['selected_category_codes']=codes;p.write_text(json.dumps(data))
                with self.assertRaises(ValueError):load_review(p)

    def test_migration_blocks_unsplit_data_then_enforces_uniqueness(self):
        migration=self.migration()
        with self.assertRaisesRegex(RuntimeError,'Shared causes'):migration.upgrade()
        execute_review(self.db,self.data,apply=True)
        migration.upgrade()
        target=self.db.scalar(select(FailureCause).where(FailureCause.code=='SHARED__A'))
        with self.assertRaises(IntegrityError):
            with self.conn.begin_nested():
                self.conn.execute(text('INSERT INTO app.failure_cause_category_link VALUES (:cause,:cat)'),{'cause':target.id,'cat':self.b.id})
        migration.downgrade()


if __name__=='__main__':unittest.main()

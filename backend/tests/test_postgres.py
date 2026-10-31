"""Run only against an explicitly selected disposable integration database."""
import os
import unittest
import psycopg


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL for PostgreSQL integration")
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(os.environ["TEST_DATABASE_URL"])
        self.cursor = self.connection.cursor()
        self.cursor.execute("INSERT INTO users(user_id,email,name,password_hash,role) VALUES ('test-owner','test@example.test','Test','hash','teacher')")
        self.cursor.execute("INSERT INTO classrooms(classroom_id,name,join_code,created_by) VALUES ('test-class','Test','TEST01','test-owner')")
        self.cursor.execute("INSERT INTO files(file_id,classroom_id,original_name,storage_path,file_type,sha256_hash,uploaded_by) VALUES ('test-file','test-class','Notes','/test','pdf','hash','test-owner')")
        self.cursor.execute("INSERT INTO file_revisions VALUES ('test-file',1,'gemini-embedding-2:1536:search-v1','test','ready')")

    def tearDown(self):
        self.connection.rollback()
        self.connection.close()

    def test_vector_and_lexical_retrieval(self):
        vector = '[' + ','.join(['1'] + ['0'] * 1535) + ']'
        self.cursor.execute("INSERT INTO chunks(chunk_id,file_id,classroom_id,revision,chunk_index,text,content_hash,embedding) VALUES ('test-chunk','test-file','test-class',1,0,'Neural networks use backpropagation','hash',%s::vector)", (vector,))
        self.cursor.execute("SELECT chunk_id FROM chunks WHERE lexical @@ plainto_tsquery('english','backpropagation') ORDER BY embedding <=> %s::vector LIMIT 1", (vector,))
        self.assertEqual(self.cursor.fetchone()[0], 'test-chunk')

    def test_file_cannot_claim_another_classroom(self):
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.cursor.execute("INSERT INTO chunks(chunk_id,file_id,classroom_id,revision,chunk_index,text,content_hash) VALUES ('bad','test-file','other',1,0,'text','hash')")

    def test_revision_must_exist_at_commit(self):
        self.cursor.execute("UPDATE files SET active_revision=99 WHERE file_id='test-file'")
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_transaction_identity_is_cleared(self):
        self.cursor.execute("SELECT set_config('app.user_id','test-owner',true)")
        self.connection.rollback()
        self.cursor.execute("SELECT current_setting('app.user_id',true)")
        self.assertIn(self.cursor.fetchone()[0], (None, ''))

    def test_rls_hides_classroom_from_nonmember(self):
        self.cursor.execute("CREATE ROLE campusconnect_test_reader NOLOGIN")
        self.cursor.execute("GRANT USAGE ON SCHEMA public TO campusconnect_test_reader")
        self.cursor.execute("GRANT SELECT ON classrooms,files,chunks,file_revisions TO campusconnect_test_reader")
        self.cursor.execute("SET LOCAL ROLE campusconnect_test_reader")
        self.cursor.execute("SELECT set_config('app.user_id','outsider',true)")
        self.cursor.execute("SELECT count(*) FROM files WHERE file_id='test-file'")
        self.assertEqual(self.cursor.fetchone()[0], 0)
        self.cursor.execute("SELECT set_config('app.user_id','test-owner',true)")
        self.cursor.execute("SELECT count(*) FROM files WHERE file_id='test-file'")
        self.assertEqual(self.cursor.fetchone()[0], 1)

    def test_rls_fails_closed_without_identity(self):
        self.cursor.execute("CREATE ROLE campusconnect_test_reader NOLOGIN")
        self.cursor.execute("GRANT USAGE ON SCHEMA public TO campusconnect_test_reader")
        self.cursor.execute("GRANT SELECT ON classrooms,files TO campusconnect_test_reader")
        self.cursor.execute("SET LOCAL ROLE campusconnect_test_reader")
        self.cursor.execute("SELECT count(*) FROM classrooms")
        self.assertEqual(self.cursor.fetchone()[0], 0)

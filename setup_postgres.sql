-- Optional database creation only. Application startup owns role and ACL setup.
-- Run as the exam PostgreSQL administrator:
-- psql -U postgres -d postgres -f setup_postgres.sql

SELECT 'CREATE DATABASE classicmodels'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'classicmodels')\gexec

SELECT 'CREATE DATABASE pagila'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'pagila')\gexec

\echo 'Master databases prepared. Start the application to provision restricted roles and load datasets.'
\echo 'sandbox_pribadi is virtual; do not grant student_role access to private schemas.'

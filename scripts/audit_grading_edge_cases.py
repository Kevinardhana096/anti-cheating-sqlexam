"""Reproduce grading edge cases on disposable PostgreSQL; never change exam scores."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_support import ensure_test_environment
ensure_test_environment()
import database as db


def main():
    nim='GRADING-AUDIT'
    db.login_student(nim,'Grading audit','testclient','audit-token','audit-device')
    cases=[]
    def case(name,answer,reference,wanted,kind='bug_probe',sandbox=False,**options):
        result=db.evaluate_sql_submission(answer,reference,10,
            target_db='sandbox_pribadi' if sandbox else 'pagila',
            active_db='sandbox_pribadi' if sandbox else 'pagila',nim=nim,**options)
        cases.append(dict(name=name,kind=kind,expected_correct=wanted,
            actual_correct=result['is_correct'],graded=result['graded'],status=result['eval_status'],
            mismatch=result['is_correct']!=wanted,answer=answer,reference=reference))
    base="SELECT * FROM (VALUES (8,'A',300),(9,'NEW',264),(9,'DRAMA',264),(10,'B',100)) t(bulan,kategori,total)"
    for order in ('bulan,total DESC','1,3 DESC','(bulan+0),total DESC','t.bulan,total DESC'):
        for direction in ('ASC','DESC'):
            case('ties '+order+' '+direction,base+' ORDER BY bulan,total DESC,kategori '+direction,base+' ORDER BY '+order,True)
    case('ordered tie with tolerance',
        "SELECT * FROM (VALUES (1,'B',1.001),(1,'A',2.001)) t(k,label,v) ORDER BY k,label DESC",
        "SELECT * FROM (VALUES (1,'A',2.0),(1,'B',1.0)) t(k,label,v) ORDER BY k",True,
        grading_policy={'numeric_absolute_tolerance':'0.01'})
    case('JSON null is not SQL NULL','SELECT NULL::jsonb AS v',"SELECT 'null'::jsonb AS v",False)
    case('JSON decimal precision',"SELECT '{\"v\":0.12345678901234567892}'::jsonb AS v",
         "SELECT '{\"v\":0.12345678901234567891}'::jsonb AS v",False)
    case('array lower bounds',"SELECT '[0:1]={1,2}'::int[] AS v",'SELECT ARRAY[1,2] AS v',False,kind='type_semantics')
    case('equivalent CHECK','CREATE TABLE t(id INT CHECK(0<id))','CREATE TABLE t(id INT CHECK(id>0))',True,sandbox=True)
    case('unique index NULL semantics','CREATE TABLE t(id INT); CREATE UNIQUE INDEX ux ON t(id)',
        'CREATE TABLE t(id INT); CREATE UNIQUE INDEX ux ON t(id) NULLS NOT DISTINCT',False,sandbox=True)
    case('unique index INCLUDE vs key','CREATE TABLE t(a INT,b INT); CREATE UNIQUE INDEX ux ON t(a,b)',
        'CREATE TABLE t(a INT,b INT); CREATE UNIQUE INDEX ux ON t(a) INCLUDE(b)',False,sandbox=True)
    case('floating arithmetic', 'SELECT (0.1::float8+0.2::float8) AS v','SELECT 0.3::numeric AS v',True,kind='policy_risk')
    case('hardcoded aggregate','SELECT 2::bigint AS n','SELECT count(*) AS n FROM (VALUES(1),(2)) t(n)',False,kind='single_dataset_limit')
    case('wrong result after preview', 'SELECT CASE WHEN n=900 THEN -1 ELSE n END AS n FROM generate_series(1,1000) n',
        'SELECT n FROM generate_series(1,1000) n',False,kind='control')
    case('duplicate rows matter','SELECT 1 AS v UNION ALL SELECT 2','SELECT 1 AS v UNION ALL SELECT 1',False,kind='control')
    case('wrong order remains wrong',base+' ORDER BY bulan DESC,total DESC',base+' ORDER BY bulan,total DESC',False,kind='control')
    controls=[
        ('integer numeric equivalence','SELECT 1.000::numeric AS v','SELECT 1 AS v',True),
        ('leading zero text differs',"SELECT '1' AS v","SELECT '001' AS v",False),
        ('boolean is not integer','SELECT 1 AS v','SELECT TRUE AS v',False),
        ('NULL is not zero','SELECT 0 AS v','SELECT NULL::int AS v',False),
        ('duplicates cannot disappear','SELECT 1 AS v UNION SELECT 1','SELECT 1 AS v UNION ALL SELECT 1',False),
        ('CASE equivalent to COALESCE','SELECT CASE WHEN a IS NULL THEN 0 ELSE a END AS v FROM (VALUES(NULL::int),(2)) t(a)',
            'SELECT COALESCE(a,0) AS v FROM (VALUES(NULL::int),(2)) t(a)',True),
        ('CTE equivalent to derived table','WITH x AS (SELECT 1 AS v) SELECT v FROM x','SELECT v FROM (SELECT 1 AS v) x',True),
        ('equivalent count null behavior','SELECT count(*) AS v FROM (VALUES(1),(NULL)) t(n) WHERE n IS NOT NULL',
            'SELECT count(n) AS v FROM (VALUES(1),(NULL)) t(n)',True),
        ('wrong count null behavior','SELECT count(*) AS v FROM (VALUES(1),(NULL)) t(n)',
            'SELECT count(n) AS v FROM (VALUES(1),(NULL)) t(n)',False),
        ('timezone equivalent instants',"SELECT TIMESTAMPTZ '2025-01-01 08:00+08' AS v", "SELECT TIMESTAMPTZ '2025-01-01 00:00+00' AS v",True),
        ('NULL ordering wrong','SELECT n FROM (VALUES(1),(NULL)) t(n) ORDER BY n NULLS FIRST',
            'SELECT n FROM (VALUES(1),(NULL)) t(n) ORDER BY n NULLS LAST',False),
    ]
    for name,answer,reference,wanted in controls:
        case(name,answer,reference,wanted,kind='control')
    case('named vs unnamed primary key','CREATE TABLE t(id INT CONSTRAINT chosen_name PRIMARY KEY)',
        'CREATE TABLE t(id INT PRIMARY KEY)',True,kind='control',sandbox=True)
    case('extra constraint detected','CREATE TABLE t(id INT UNIQUE)','CREATE TABLE t(id INT)',False,kind='control',sandbox=True)
    case('LIMIT tied boundary',"SELECT label FROM (VALUES(10,'B'),(10,'A')) t(amount,label) ORDER BY amount DESC,label DESC LIMIT 1",
        "SELECT label FROM (VALUES(10,'A'),(10,'B')) t(amount,label) ORDER BY amount DESC LIMIT 1",True,kind='ambiguous_specification')
    destination=Path(sys.argv[1]) if len(sys.argv)>1 else Path('scratch/grading-audit.json')
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(cases,indent=2),encoding='utf-8')
    for row in cases:
        print(('MISMATCH' if row['mismatch'] else 'OK'),row['name'],row['status'],flush=True)
    print(f'{len(cases)} cases; {sum(c["mismatch"] for c in cases)} expectation differences; {destination}',flush=True)
    db.cleanup_student_sandbox_schema(nim)


if __name__=='__main__':
    main()

import os
import fdb
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import datetime
import logging
import time

from config import (
    HOST, PORT, FRONTEND_PORT, DB_HOST, DB_DIR, DB_USER, DB_PASSWORD,
    DEFAULT_ROOM_CODE, DEFAULT_ROOM_NAME,
    DEFAULT_DEPT_CODE, DEFAULT_DEPT_NAME,
    DEFAULT_DOCTOR_CODE, DEFAULT_DOCTOR_NAME
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("emr_api")

# Configure fdb charset mappings BEFORE establishing connections.
# This ensures CP949 bytes are correctly decoded into Unicode on all platforms.
fdb.charset_map['NONE'] = 'cp949'
fdb.charset_map[None] = 'cp949'
fdb.charset_map['KSC_5601'] = 'cp949'

# Import decryptor
try:
    from decryptor import get_decryptor
    decrypt_client = get_decryptor()
except Exception as e:
    logger.critical(f"Failed to initialize decryptor: {e}")
    decrypt_client = None

app = FastAPI(
    title="mart clinic gateway API",
    description="REST API mediator for local Firebird EMR databases with native 32-bit decryption.",
    version="1.0.0"
)

# Enable CORS for local testing/integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Frontend Application Server (Self Check-In UI)
frontend_app = FastAPI(
    title="EMR self-registration UI",
    description="Serves the self-registration / self check-in kiosk UI on port 3007.",
    version="1.0.0"
)

frontend_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@frontend_app.get("/config.js")
def get_frontend_config():
    """Serves backend port configuration dynamically to the frontend client."""
    return Response(
        content=f"window.GATEWAY_PORT = {PORT};",
        media_type="application/javascript"
    )

# Mount the registration UI static files
frontend_app.mount("/", StaticFiles(directory="registration-ui", html=True), name="registration-ui")

# Database Logging Wrappers
class LoggingCursor:
    def __init__(self, cursor, db_name: str):
        self._cursor = cursor
        self._db_name = db_name

    def execute(self, query, params=None):
        start_time = time.time()
        params_str = f" | Params: {params}" if params else ""
        logger.info(f"[DB QUERY] [{self._db_name}] SQL: {query.strip()}{params_str}")
        try:
            res = self._cursor.execute(query, params)
            duration = (time.time() - start_time) * 1000
            logger.info(f"[DB QUERY SUCCESS] [{self._db_name}] Took {duration:.2f}ms")
            return res
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(f"[DB QUERY FAILURE] [{self._db_name}] Took {duration:.2f}ms | Error: {e}")
            raise

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchone(self):
        return self._cursor.fetchone()

    @property
    def description(self):
        return self._cursor.description

    def __getattr__(self, name):
        return getattr(self._cursor, name)

class LoggingConnection:
    def __init__(self, connection, db_name: str):
        self._connection = connection
        self._db_name = db_name
        logger.info(f"[DB TRANSACTION] [{self._db_name}] Connection opened & transaction started")

    def cursor(self):
        return LoggingCursor(self._connection.cursor(), self._db_name)

    def commit(self):
        start_time = time.time()
        logger.info(f"[DB TRANSACTION] [{self._db_name}] Committing...")
        try:
            self._connection.commit()
            logger.info(f"[DB TRANSACTION SUCCESS] [{self._db_name}] Committed (took {(time.time() - start_time)*1000:.2f}ms)")
        except Exception as e:
            logger.error(f"[DB TRANSACTION FAILURE] [{self._db_name}] Commit failed: {e}")
            raise

    def rollback(self):
        start_time = time.time()
        logger.info(f"[DB TRANSACTION] [{self._db_name}] Rolling back...")
        try:
            self._connection.rollback()
            logger.info(f"[DB TRANSACTION SUCCESS] [{self._db_name}] Rolled back (took {(time.time() - start_time)*1000:.2f}ms)")
        except Exception as e:
            logger.error(f"[DB TRANSACTION FAILURE] [{self._db_name}] Rollback failed: {e}")
            raise

    def close(self):
        start_time = time.time()
        logger.info(f"[DB TRANSACTION] [{self._db_name}] Closing connection...")
        try:
            self._connection.close()
            logger.info(f"[DB TRANSACTION SUCCESS] [{self._db_name}] Connection closed (took {(time.time() - start_time)*1000:.2f}ms)")
        except Exception as e:
            logger.error(f"[DB TRANSACTION FAILURE] [{self._db_name}] Connection close failed: {e}")
            raise

    def __getattr__(self, name):
        return getattr(self._connection, name)

# Helper: Connect to Firebird DB
def get_db_connection(db_name: str):
    db_path = os.path.join(DB_DIR, f"{db_name}.FDB")
    is_local = DB_HOST in ("127.0.0.1", "localhost")
    if is_local and not os.path.exists(db_path):
        logger.error(f"[DB CONNECTION ERROR] Database file not found locally: {db_path}")
        raise HTTPException(status_code=500, detail=f"Database file not found locally: {db_path}")
    try:
        con = fdb.connect(
            dsn=f"{DB_HOST}:{db_path}",
            user=DB_USER,
            password=DB_PASSWORD
        )
        return LoggingConnection(con, db_name)
    except Exception as e:
        logger.error(f"[DB CONNECTION ERROR] Failed to connect to database {db_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect to database {db_name}: {e}")

# Helper: Get all annual tables matching a prefix (e.g. CHT2025, WAIT2025)
def get_annual_tables(db_name: str, prefix: str) -> List[str]:
    try:
        con = get_db_connection(db_name)
        cur = con.cursor()
        cur.execute("SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG = 0")
        tables = [r[0].strip() for r in cur.fetchall()]
        con.close()
        
        # Filter tables matching prefix + 4 digits (e.g., CHT2024)
        annual_tables = []
        for t in tables:
            if t.startswith(prefix) and len(t) == len(prefix) + 4:
                year_part = t[len(prefix):]
                if year_part.isdigit():
                    annual_tables.append(t)
        return sorted(annual_tables, reverse=True)
    except Exception as e:
        logger.error(f"Error finding annual tables in {db_name} for prefix {prefix}: {e}")
        return []

# Helper: JSON serializer for Date/Time objects
def serialize_row(cols, vals):
    row_dict = {}
    for k, v in zip(cols, vals):
        if isinstance(v, (datetime.date, datetime.datetime)):
            row_dict[k.lower()] = v.isoformat()
        elif isinstance(v, datetime.time):
            row_dict[k.lower()] = v.strftime("%H:%M:%S")
        elif isinstance(v, str):
            row_dict[k.lower()] = v.strip()
        else:
            row_dict[k.lower()] = v
    return row_dict

# Endpoints
@app.get("/api/schema")
def get_schema():
    """Dynamically returns the schema (tables, columns, types) of all four databases."""
    databases = ["MTSDB", "MTSCHT", "MTSWAIT", "MTSMTR"]
    schema_results = {}
    
    type_names = {
        7: "SMALLINT", 8: "INTEGER", 10: "FLOAT", 12: "DATE", 13: "TIME", 
        14: "CHAR", 16: "BIGINT", 27: "DOUBLE", 35: "TIMESTAMP", 37: "VARCHAR", 261: "BLOB"
    }
    
    for db in databases:
        try:
            con = get_db_connection(db)
            cur = con.cursor()
            query = """
                SELECT rf.RDB$RELATION_NAME, rf.RDB$FIELD_NAME, f.RDB$FIELD_TYPE, f.RDB$FIELD_LENGTH
                FROM RDB$RELATION_FIELDS rf
                JOIN RDB$FIELDS f ON rf.RDB$FIELD_SOURCE = f.RDB$FIELD_NAME
                JOIN RDB$RELATIONS r ON rf.RDB$RELATION_NAME = r.RDB$RELATION_NAME
                WHERE r.RDB$SYSTEM_FLAG = 0
                ORDER BY rf.RDB$RELATION_NAME, rf.RDB$FIELD_POSITION
            """
            cur.execute(query)
            db_schema = {}
            for r in cur.fetchall():
                tbl = r[0].strip()
                fld = r[1].strip()
                typ = r[2]
                length = r[3]
                typ_name = type_names.get(typ, f"UNKNOWN ({typ})")
                
                if tbl not in db_schema:
                    db_schema[tbl] = []
                db_schema[tbl].append({
                    "column": fld,
                    "type": typ_name,
                    "length": length
                })
            con.close()
            schema_results[db] = db_schema
        except Exception as e:
            schema_results[db] = {"error": str(e)}
            
    return schema_results

@app.get("/api/patients")
def get_patients(
    pname: Optional[str] = Query(None, description="Filter by Patient Name"),
    pcode: Optional[int] = Query(None, description="Filter by exact Patient Code"),
    limit: int = Query(50, description="Limit records returned")
):
    """Queries MTSDB.PERSON table and decrypts PIDNUM fields on-the-fly."""
    con = get_db_connection("MTSDB")
    cur = con.cursor()
    
    try:
        sql = "SELECT PCODE, PNAME, PBIRTH, PIDNUM, SEX, LASTCHECK, PHONENUM FROM PERSON"
        params = []
        conditions = []
        
        # We need to see if PHONENUM exists in PERSON table. Since we don't know for sure, 
        # let's select it. If it fails, we fall back.
        # Wait, the column list we printed earlier had:
        # PCODE, FCODE, PNAME, PBIRTH, PIDNUM, SEX, RELATION, LASTCHECK, SEARCHID, ...
        # Let's check if PHONENUM exists in PERSON. The column list had:
        # 'SEARCHID': '030926-3', 'PCCHECK': None, ...
        # Oh, PHONENUM was in MTSMTR tables but was it in PERSON? Let's check PERSON column names.
        # It had PCODE, FCODE, PNAME, PBIRTH, PIDNUM, SEX, RELATION, RELATION2, CRIPPLED, BOHUN, BP, BLOODTYPE, LASTCHECK...
        # Wait, was PHONENUM in PERSON? No, it wasn't in the list printed earlier!
        # Let's select only: PCODE, PNAME, PBIRTH, PIDNUM, SEX, LASTCHECK.
        sql = "SELECT PCODE, PNAME, PBIRTH, PIDNUM, SEX, LASTCHECK FROM PERSON"
        
        if pcode is not None:
            conditions.append("PCODE = ?")
            params.append(pcode)
        if pname:
            conditions.append("PNAME LIKE ?")
            params.append(f"%{pname}%")
            
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
            
        sql += f" ORDER BY PCODE DESC"
        
        # Firebird 2.5 uses "FIRST N" instead of "LIMIT N"
        sql = sql.replace("SELECT", f"SELECT FIRST {limit}")
        
        cur.execute(sql, tuple(params))
        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        
        results = []
        for r in rows:
            p_dict = serialize_row(cols, r)
            # Decrypt the resident number if present
            pidnum_enc = p_dict.get("pidnum")
            if pidnum_enc and decrypt_client:
                p_dict["pidnum_decrypted"] = decrypt_client.decrypt(pidnum_enc)
            else:
                p_dict["pidnum_decrypted"] = pidnum_enc
            results.append(p_dict)
            
        con.close()
        return results
    except Exception as e:
        con.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/patients/{pcode}")
def get_patient_detail(pcode: int):
    """Fetches details for a single patient, including their vitals."""
    con_db = get_db_connection("MTSDB")
    cur_db = con_db.cursor()
    
    try:
        # Query patient
        cur_db.execute("SELECT PCODE, PNAME, PBIRTH, PIDNUM, SEX, LASTCHECK FROM PERSON WHERE PCODE = ?", (pcode,))
        patient = cur_db.fetchone()
        if not patient:
            con_db.close()
            raise HTTPException(status_code=404, detail="Patient not found")
            
        cols_db = [desc[0] for desc in cur_db.description]
        patient_dict = serialize_row(cols_db, patient)
        
        # Decrypt RRN
        pidnum_enc = patient_dict.get("pidnum")
        if pidnum_enc and decrypt_client:
            patient_dict["pidnum_decrypted"] = decrypt_client.decrypt(pidnum_enc)
        else:
            patient_dict["pidnum_decrypted"] = pidnum_enc
            
        # Query Vitals from CHECK_VITAL in MTSDB
        cur_db.execute("SELECT VISIDATE, CHKTIME, WEIGHT, HEIGHT, TEMPERATUR, PULSE, SYSTOLIC, DIASTOLIC FROM CHECK_VITAL WHERE PCODE = ? ORDER BY VISIDATE DESC, CHKTIME DESC", (pcode,))
        vitals_rows = cur_db.fetchall()
        cols_v = [desc[0] for desc in cur_db.description]
        
        vitals_list = []
        for v in vitals_rows:
            vitals_list.append(serialize_row(cols_v, v))
            
        patient_dict["vitals"] = vitals_list
        con_db.close()
        return patient_dict
    except HTTPException:
        raise
    except Exception as e:
        con_db.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/waiting")
def get_waiting(
    source: str = Query(
        "mtsmtr",
        pattern="^(mtswait|mtsmtr)$",
        description="Choose which source to fetch from: mtswait or mtsmtr."
    )
):
    """Queries today's queue from either MTSWAIT or MTSMTR.

    By default, this returns MTSMTR (ledger) entries for the current date. Use source=mtswait
    to fetch the live queue from MTSWAIT instead.
    """
    today = datetime.date.today()
    source = source.lower()
    active_table = None

    if source == "mtswait":
        wait_records, active_table = fetch_today_queue("MTSWAIT", "WAIT", today)
        if not wait_records:
            return {"source": source, "active_table": active_table, "queue": []}

        pcodes = list(set([r["pcode"] for r in wait_records if r.get("pcode")]))
        patient_map = {}
        if pcodes:
            con_db = get_db_connection("MTSDB")
            cur_db = con_db.cursor()
            try:
                pcode_placeholders = ",".join(["?" for _ in pcodes])
                sql = f"SELECT PCODE, PNAME, PBIRTH, SEX, PIDNUM FROM PERSON WHERE PCODE IN ({pcode_placeholders})"
                cur_db.execute(sql, tuple(pcodes))
                cols_p = [desc[0] for desc in cur_db.description]
                for r in cur_db.fetchall():
                    p_dict = serialize_row(cols_p, r)
                    pidnum_enc = p_dict.get("pidnum")
                    if pidnum_enc and decrypt_client:
                        p_dict["pidnum_decrypted"] = decrypt_client.decrypt(pidnum_enc)
                    else:
                        p_dict["pidnum_decrypted"] = pidnum_enc
                    patient_map[p_dict["pcode"]] = p_dict
            except Exception as e:
                logger.error(f"Failed to join patient details: {e}")
            finally:
                con_db.close()

        for r in wait_records:
            pcode = r.get("pcode")
            r["patient"] = patient_map.get(pcode)

        return {"source": source, "active_table": active_table, "queue": wait_records}

    if source == "mtsmtr":
        mtr_records, active_table = fetch_today_queue("MTSMTR", "MTR", today)
        return {"source": source, "active_table": active_table, "queue": mtr_records}


@app.get("/api/waiting/compare")
def compare_waiting():
    """Returns today's current-date queue from both MTSWAIT and MTSMTR for side-by-side comparison."""
    today = datetime.date.today()
    wait_records, wait_table = fetch_today_queue("MTSWAIT", "WAIT", today)
    mtr_records, mtr_table = fetch_today_queue("MTSMTR", "MTR", today)
    return {
        "date": today.isoformat(),
        "mtswait": {"active_table": wait_table, "queue": wait_records},
        "mtsmtr": {"active_table": mtr_table, "queue": mtr_records}
    }

class WaitlistCreate(BaseModel):
    pcode: int
    roomcode: Optional[int] = DEFAULT_ROOM_CODE
    roomnm: Optional[str] = DEFAULT_ROOM_NAME
    deptcode: Optional[str] = DEFAULT_DEPT_CODE
    deptnm: Optional[str] = DEFAULT_DEPT_NAME
    doctrcode: Optional[str] = DEFAULT_DOCTOR_CODE
    doctrnm: Optional[str] = DEFAULT_DOCTOR_NAME

class WaitlistUpdate(BaseModel):
    roomcode: Optional[int] = None
    roomnm: Optional[str] = None
    deptcode: Optional[str] = None
    deptnm: Optional[str] = None
    doctrcode: Optional[str] = None
    doctrnm: Optional[str] = None

def calculate_age_str(birthdate: datetime.date) -> str:
    if not birthdate:
        return ""
    today = datetime.date.today()
    years = today.year - birthdate.year
    months = today.month - birthdate.month
    if months < 0:
        years -= 1
        months += 12
    if years > 0:
        if months > 0:
            return f"{years}y {months}m "
        else:
            return f"{years}y "
    else:
        return f"{months}m "

def get_active_table(db_name: str, prefix: str) -> str:
    current_year = datetime.date.today().year
    table_name = f"{prefix}{current_year}"
    tables = get_annual_tables(db_name, prefix)
    if table_name in tables:
        return table_name
    elif tables:
        return tables[0]
    else:
        raise HTTPException(status_code=500, detail=f"No {prefix}[YYYY] tables found in {db_name} database.")


def fetch_today_queue(db_name: str, prefix: str, today: datetime.date, limit: int = 50):
    table_name = get_active_table(db_name, prefix)
    con = get_db_connection(db_name)
    cur = con.cursor()
    rows = []
    try:
        if db_name == "MTSWAIT":
            sql = f"SELECT FIRST {limit} PCODE, VISIDATE, RESID1, ROOMNM, DEPTNM, DOCTRNM, DOCTRCODE FROM {table_name} WHERE VISIDATE = ? ORDER BY RESID1 DESC"
        else:
            sql = f"SELECT FIRST {limit} PCODE, VISIDATE, VISITIME, PNAME, SEX, PBIRTH, AGE, FIN, SERIAL FROM {table_name} WHERE VISIDATE = ? ORDER BY VISITIME DESC"
        cur.execute(sql, (today,))
        cols = [desc[0] for desc in cur.description]
        rows = [serialize_row(cols, r) for r in cur.fetchall()]
        if db_name == "MTSMTR":
            for r in rows:
                vd = r.get("visidate", "")
                vt = r.get("visitime", "")
                pcode = r.get("pcode", "")
                if vd and vt and pcode is not None:
                    vd_clean = vd.replace("-", "")
                    vt_clean = vt.replace(":", "")[:4]
                    r["resid1"] = f"{vd_clean}{vt_clean}{pcode}"
    except Exception as e:
        logger.error(f"Error querying today's queue from {db_name}.{table_name}: {e}")
    finally:
        con.close()
    return rows, table_name


def get_table_from_resid1(db_name: str, prefix: str, resid1: str) -> str:
    if len(resid1) >= 4 and resid1[:4].isdigit():
        year = resid1[:4]
        tbl = f"{prefix}{year}"
        tables = get_annual_tables(db_name, prefix)
        if tbl in tables:
            return tbl
    return get_active_table(db_name, prefix)


@app.post("/api/waiting")
def check_in_patient(req: WaitlistCreate):
    """Checks in a patient by creating a ledger record in MTSMTR only.

    The live wait queue (MTSWAIT) is not modified by this endpoint.
    """
    # 1. Fetch patient demographics from MTSDB
    con_db = get_db_connection("MTSDB")
    cur_db = con_db.cursor()
    try:
        cur_db.execute("SELECT PCODE, PNAME, PBIRTH, SEX FROM PERSON WHERE PCODE = ?", (req.pcode,))
        patient = cur_db.fetchone()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient with code {req.pcode} not found.")
        pname, pbirth, sex = patient[1], patient[2], patient[3]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching patient {req.pcode}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        con_db.close()

    # Determine MTR table
    mtr_table = get_active_table("MTSMTR", "MTR")

    today = datetime.date.today()
    now_time = datetime.datetime.now().time()
    current_time_str = now_time.strftime("%H:%M:%S")

    # Generate keys (resid1 kept for compatibility with clients if needed)
    resid1 = f"{today.strftime('%Y%m%d')}{now_time.strftime('%H%M')}{req.pcode}"
    resid2 = today.strftime("%Y-%m-%d")
    age_str = calculate_age_str(pbirth)

    # Insert into MTSMTR (Ledger) only
    con_mtr = get_db_connection("MTSMTR")
    cur_mtr = con_mtr.cursor()
    try:
        generator_name = f"GEN_{mtr_table}_SEQ"
        cur_mtr.execute(f"SELECT GEN_ID({generator_name}, 1) FROM RDB$DATABASE")
        next_id = cur_mtr.fetchone()[0]

        sql_mtr = f"""
            INSERT INTO {mtr_table} 
            ("#", PCODE, VISIDATE, VISITIME, PNAME, SEX, PBIRTH, AGE, FIN, SERIAL, GUBUN)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cur_mtr.execute(sql_mtr, (next_id, req.pcode, today, current_time_str, pname, sex, pbirth, age_str, '', 1, '셀프'))
        con_mtr.commit()
        logger.info(f"Created ledger record in {mtr_table} with ID {next_id} for patient {req.pcode}")
    except Exception as e:
        logger.error(f"Error inserting into MTSMTR: {e}")
        con_mtr.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create ledger record in MTSMTR: {e}")
    finally:
        con_mtr.close()

    return {
        "status": "success",
        "message": f"Patient {pname} ledger created successfully.",
        "mtr_id": next_id,
        "resid1": resid1,
        "pcode": req.pcode
    }


class CloudMtrCreate(BaseModel):
    """API model for cloud clients to create MTR ledger records.

    Clients may provide `pname` and `pbirth` to avoid an extra lookup in `MTSDB`.
    The server will fall back to `MTSDB` if those fields are missing or invalid.
    """
    pcode: int
    pname: Optional[str] = None
    pbirth: Optional[datetime.date] = None
    roomcode: Optional[int] = DEFAULT_ROOM_CODE
    roomnm: Optional[str] = DEFAULT_ROOM_NAME
    deptcode: Optional[str] = DEFAULT_DEPT_CODE
    deptnm: Optional[str] = DEFAULT_DEPT_NAME
    doctrcode: Optional[str] = DEFAULT_DOCTOR_CODE
    doctrnm: Optional[str] = DEFAULT_DOCTOR_NAME


@app.post("/api/mtr")
def create_mtr_cloud(req: CloudMtrCreate):
    """Create an MTSMTR ledger record (cloud/client-initiated).

    Verifies that the patient exists in the PERSON table (MTSDB) before creating the record.
    """
    con_db = get_db_connection("MTSDB")
    cur_db = con_db.cursor()
    try:
        cur_db.execute("SELECT PCODE, PNAME, PBIRTH, SEX FROM PERSON WHERE PCODE = ?", (req.pcode,))
        patient = cur_db.fetchone()
        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient with code {req.pcode} not found in PERSON table.")
        
        db_pcode, db_pname, db_pbirth, db_sex = patient[0], patient[1], patient[2], patient[3]
        
        # If client provided pname/pbirth, verify they match EMR database records
        if req.pname and req.pname.strip() != db_pname.strip():
            raise HTTPException(status_code=400, detail="Provided patient name does not match EMR database records.")
            
        if req.pbirth:
            # Handle possible types for db_pbirth (datetime.date, datetime.datetime, or string)
            if isinstance(db_pbirth, (datetime.date, datetime.datetime)):
                db_pbirth_date = db_pbirth if isinstance(db_pbirth, datetime.date) else db_pbirth.date()
            else:
                try:
                    db_pbirth_date = datetime.datetime.strptime(str(db_pbirth).strip(), "%Y-%m-%d").date()
                except ValueError:
                    db_pbirth_date = None
            
            if db_pbirth_date and req.pbirth != db_pbirth_date:
                raise HTTPException(status_code=400, detail="Provided birthdate does not match EMR database records.")
                
        pname = db_pname
        pbirth = db_pbirth
        sex = db_sex
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching/verifying patient {req.pcode}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        con_db.close()

    # Determine MTR table and time values
    mtr_table = get_active_table("MTSMTR", "MTR")
    today = datetime.date.today()
    now_time = datetime.datetime.now().time()
    current_time_str = now_time.strftime("%H:%M:%S")
    resid1 = f"{today.strftime('%Y%m%d')}{now_time.strftime('%H%M')}{req.pcode}"
    age_str = calculate_age_str(pbirth) if pbirth else ""

    # Insert ledger record
    con_mtr = get_db_connection("MTSMTR")
    cur_mtr = con_mtr.cursor()
    try:
        generator_name = f"GEN_{mtr_table}_SEQ"
        cur_mtr.execute(f"SELECT GEN_ID({generator_name}, 1) FROM RDB$DATABASE")
        next_id = cur_mtr.fetchone()[0]

        sql_mtr = f"""
            INSERT INTO {mtr_table} 
            ("#", PCODE, VISIDATE, VISITIME, PNAME, SEX, PBIRTH, AGE, FIN, SERIAL, GUBUN)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cur_mtr.execute(sql_mtr, (next_id, req.pcode, today, current_time_str, pname, sex or '', pbirth, age_str, '', 1, '콜닥'))
        con_mtr.commit()
        logger.info(f"[CLOUD] Created ledger record in {mtr_table} with ID {next_id} for patient {req.pcode}")
    except Exception as e:
        logger.error(f"Error inserting into MTSMTR (cloud): {e}")
        con_mtr.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create ledger record in MTSMTR: {e}")
    finally:
        con_mtr.close()

    return {"status": "success", "mtr_id": next_id, "resid1": resid1, "pcode": req.pcode}

@app.delete("/api/waiting/{resid1}")
def remove_from_waitlist(resid1: str):
    mtr_table = get_table_from_resid1("MTSMTR", "MTR", resid1)

    # Parse resid1 to retrieve pcode and visidate
    # Format: YYYYMMDDHHMM<pcode>
    if len(resid1) >= 13 and resid1[:12].isdigit():
        try:
            yr = int(resid1[:4])
            mo = int(resid1[4:6])
            dy = int(resid1[6:8])
            visidate = datetime.date(yr, mo, dy)
            pcode = int(resid1[12:])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid waitlist entry ID format.")
    else:
        raise HTTPException(status_code=400, detail="Invalid waitlist entry ID format.")

    # Delete from MTSMTR
    con_mtr = get_db_connection("MTSMTR")
    cur_mtr = con_mtr.cursor()
    try:
        # Check if a ledger record exists and its FIN state
        cur_mtr.execute(f"SELECT FIN FROM {mtr_table} WHERE PCODE = ? AND VISIDATE = ?", (pcode, visidate))
        mtr_row = cur_mtr.fetchone()
        if not mtr_row:
            raise HTTPException(status_code=404, detail="Waitlist record not found in MTSMTR.")
            
        fin_val = mtr_row[0]
        # If treatment has NOT completed (FIN is empty or null)
        if not fin_val or fin_val.strip() == "":
            cur_mtr.execute(f"DELETE FROM {mtr_table} WHERE PCODE = ? AND VISIDATE = ?", (pcode, visidate))
            con_mtr.commit()
            logger.info(f"Cancelled ledger record in {mtr_table} for patient {pcode} on {visidate} (FIN is empty)")
        else:
            logger.info(f"Kept ledger record in {mtr_table} for patient {pcode} on {visidate} (FIN is completed: {repr(fin_val)})")
            raise HTTPException(status_code=400, detail="Cannot delete a completed treatment record.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling ledger cancellation: {e}")
        con_mtr.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete waitlist record: {e}")
    finally:
        con_mtr.close()

    return {"status": "success", "message": "Patient removed from waitlist."}

@app.put("/api/waiting/{resid1}")
def update_waitlist_assignment(resid1: str, req: WaitlistUpdate):
    mtr_table = get_table_from_resid1("MTSMTR", "MTR", resid1)

    # Parse resid1 to retrieve pcode and visidate
    if len(resid1) >= 13 and resid1[:12].isdigit():
        try:
            yr = int(resid1[:4])
            mo = int(resid1[4:6])
            dy = int(resid1[6:8])
            visidate = datetime.date(yr, mo, dy)
            pcode = int(resid1[12:])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid waitlist entry ID format.")
    else:
        raise HTTPException(status_code=400, detail="Invalid waitlist entry ID format.")

    # We only have DOC column in MTSMTR to represent the doctor
    # If they passed doctrcode, we update DOC.
    updates = []
    params = []
    
    if req.doctrcode is not None:
        updates.append("DOC = ?")
        params.append(req.doctrcode)

    # If they updated other fields that don't exist in MTSMTR, we can just return success
    if not updates:
        return {"status": "success", "message": "No modifiable fields for MTSMTR provided."}

    params.extend([pcode, visidate])
    sql = f"UPDATE {mtr_table} SET {', '.join(updates)} WHERE PCODE = ? AND VISIDATE = ?"

    con_mtr = get_db_connection("MTSMTR")
    cur_mtr = con_mtr.cursor()
    try:
        cur_mtr.execute(sql, tuple(params))
        con_mtr.commit()
        logger.info(f"Updated MTSMTR doctor assignment for patient {pcode} on {visidate}")
    except Exception as e:
        logger.error(f"Error updating MTSMTR: {e}")
        con_mtr.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update ledger record: {e}")
    finally:
        con_mtr.close()

    return {"status": "success", "message": "Waitlist entry updated successfully."}

@app.get("/api/charts/{pcode}")
def get_charts(pcode: int):
    """Returns all medical chart records (symptoms, diagnoses, prescriptions) for a patient."""
    tables = get_annual_tables("MTSCHT", "CHT")
    if not tables:
        return []
        
    con_cht = get_db_connection("MTSCHT")
    cur_cht = con_cht.cursor()
    
    all_charts = []
    
    # Scan through CHT[YYYY] tables for patient records
    for t in tables:
        try:
            # We select common fields. If columns differ slightly, we catch error
            # CHT has: VISIDATE, VISITIME, SYMPTOM, D1, D2, DOC
            sql = f"SELECT VISIDATE, VISITIME, SYMPTOM, D1, D2, D3, D4, DOC FROM {t} WHERE PCODE = ? ORDER BY VISIDATE DESC"
            cur_cht.execute(sql, (pcode,))
            cols = [desc[0] for desc in cur_cht.description]
            rows = cur_cht.fetchall()
            for r in rows:
                c_dict = serialize_row(cols, r)
                c_dict["source_table"] = t
                all_charts.append(c_dict)
        except Exception as e:
            # Table might not contain fields or table doesn't exist
            continue
            
    con_cht.close()
    
    # Sort charts globally by visit date descending
    all_charts.sort(key=lambda x: x.get("visidate", ""), reverse=True)
    return all_charts

@app.get("/api/visits/{pcode}")
def get_visits(pcode: int):
    """Returns historical billing, vaccinations, physical vitals, and memos from MTSMTR."""
    tables = get_annual_tables("MTSMTR", "MTR")
    if not tables:
        return []
        
    con_mtr = get_db_connection("MTSMTR")
    cur_mtr = con_mtr.cursor()
    
    all_visits = []
    
    for t in tables:
        try:
            # MTR contains: VISIDATE, VISITIME, WEIGHT, HEIGHT, TEMPERATUR, PULSE, SYSTOLIC, DIASTOLIC,
            # TOTALFEE, SELFEE, GENFEE, AGE, VAX, INJ1
            sql = f"""
                SELECT VISIDATE, VISITIME, WEIGHT, HEIGHT, TEMPERATUR, PULSE, 
                       SYSTOLIC, DIASTOLIC, TOTALFEE, SELFEE, GENFEE, AGE, 
                       VAX, VAX2, INJ1, INJ2 
                FROM {t} WHERE PCODE = ? 
                ORDER BY VISIDATE DESC
            """
            cur_mtr.execute(sql, (pcode,))
            cols = [desc[0] for desc in cur_mtr.description]
            rows = cur_mtr.fetchall()
            for r in rows:
                v_dict = serialize_row(cols, r)
                v_dict["source_table"] = t
                all_visits.append(v_dict)
        except Exception as e:
            continue
            
    con_mtr.close()
    
    all_visits.sort(key=lambda x: x.get("visidate", ""), reverse=True)
    return all_visits

# Serve single-page dashboard at root
@app.get("/")
def read_index():
    static_index = os.path.join("static", "index.html")
    if not os.path.exists(static_index):
        raise HTTPException(status_code=404, detail=f"static/index.html not found.")
    return FileResponse(static_index)

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    import threading
    import sys

    def run_rest_server():
        logger.info(f"Starting EMR Gateway REST Server on http://{HOST}:{PORT}")
        uvicorn.run(app, host=HOST, port=PORT, log_level="info")

    def run_frontend_server():
        logger.info(f"Starting Self Check-In Frontend Server on http://{HOST}:{FRONTEND_PORT}")
        uvicorn.run(frontend_app, host=HOST, port=FRONTEND_PORT, log_level="info")

    # Run both servers concurrently in daemon threads
    rest_thread = threading.Thread(target=run_rest_server, daemon=True)
    frontend_thread = threading.Thread(target=run_frontend_server, daemon=True)

    rest_thread.start()
    frontend_thread.start()

    # Keep the main thread alive to handle keyboard interrupt
    try:
        while True:
            rest_thread.join(0.5)
            frontend_thread.join(0.5)
            if not rest_thread.is_alive() or not frontend_thread.is_alive():
                logger.info("One of the servers stopped. Shutting down...")
                break
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Stopping both servers...")
        sys.exit(0)

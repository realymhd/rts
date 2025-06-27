import sys
import pandas as pd
from sqlalchemy import create_engine, text
import re

def load_db_credentials(secrets_path=".streamlit/secrets.toml"):
    """
    .streamlit/secrets.toml 파일에서 데이터베이스 접속 정보를 읽어옵니다.
    """
    credentials = {}
    try:
        with open(secrets_path, 'r', encoding='utf-8') as f:
            in_database_section = False
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if line == '[database]':
                    in_database_section = True
                    continue
                
                if line.startswith('['):
                    in_database_section = False
                    continue

                if in_database_section:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"') # 따옴표 제거
                    # 포트는 정수형으로 변환
                    if key == 'port':
                        credentials[key] = int(value)
                    else:
                        credentials[key] = value
        return credentials
    except FileNotFoundError:
        print(f"Error: Secrets file not found at '{secrets_path}'")
        return None
    except Exception as e:
        print(f"Error reading secrets file: {e}")
        return None

def run_sql_file(filepath, db_creds):
    """
    주어진 경로의 SQL 파일에 포함된 모든 쿼리를 실행하고 결과를 출력합니다.
    """
    if not db_creds:
        print("Database credentials are not available. Exiting.")
        return

    try:
        engine = create_engine(
            f"mysql+pymysql://{db_creds['user']}:{db_creds['password']}@{db_creds['host']}:{db_creds['port']}/{db_creds['dbname']}"
        )

        with open(filepath, 'r', encoding='utf-8') as f:
            # 주석을 먼저 제거합니다.
            sql_script = re.sub(r'--.*', '', f.read())
            # 세미콜론(;)으로 쿼리들을 분리합니다.
            queries = [q.strip() for q in sql_script.split(';') if q.strip()]

        with engine.connect() as connection:
            for i, query_string in enumerate(queries):
                if not query_string:
                    continue
                
                print(f"--- Query #{i+1} Result ---")
                print(f"Executing: {query_string[:200]}...") # 쿼리 미리보기
                try:
                    # SELECT 쿼리는 결과를 DataFrame으로 예쁘게 출력합니다.
                    if query_string.upper().strip().startswith("SELECT"):
                        df = pd.read_sql(text(query_string), connection)
                        print(df.to_markdown(index=False))
                    else:
                        # 다른 유형의 쿼리는 실행만 합니다 (결과가 없는 경우 대비).
                        connection.execute(text(query_string))
                        print(f"Query executed successfully (no result to display).")

                except Exception as e:
                    print(f"Error executing query: {e}")
                print("\n" + "="*50 + "\n")

    except FileNotFoundError:
        print(f"Error: SQL file not found at '{filepath}'")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        db_credentials = load_db_credentials()
        sql_file_path = sys.argv[1]
        run_sql_file(sql_file_path, db_credentials)
    else:
        print("Usage: python3 run_sql.py <path_to_sql_file>") 
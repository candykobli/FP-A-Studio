"""Opt-in external connectors. Secrets never saved to files by the app."""
import pandas as pd
import requests
from sqlalchemy import create_engine, text


def read_sql(connection_url, query):
    if not query.strip().lower().startswith('select') and not query.strip().lower().startswith('with'):
        raise ValueError('Only SELECT/WITH queries are accepted.')
    engine=create_engine(connection_url,connect_args={} if 'sqlite' in connection_url else {})
    try:
        with engine.connect() as connection:
            connection=connection.execution_options(isolation_level='AUTOCOMMIT')
            return pd.read_sql_query(text(query),connection)
    finally: engine.dispose()


def read_api(url, token=None, records_path=None):
    if not url.lower().startswith('https://'):
        raise ValueError('API URL must use HTTPS.')
    headers={'Authorization':f'Bearer {token}'} if token else {}
    response=requests.get(url,headers=headers,timeout=20,allow_redirects=False)
    response.raise_for_status()
    obj=response.json()
    if records_path:
        for key in records_path.split('.'):
            obj=obj[key]
    elif isinstance(obj,dict):
        for key in ('data','results','records','items'):
            if isinstance(obj.get(key),list):obj=obj[key];break
    return pd.json_normalize(obj)

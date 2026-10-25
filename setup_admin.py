"""Open the one-time local admin setup; never print the setup secret."""
from pathlib import Path
from urllib.parse import urlencode
import webbrowser
import db

if __name__=='__main__':
    code=Path(db.DB).with_suffix('.admin-setup-code')
    if code.is_file():
        token=code.read_text(encoding='utf-8').strip()
        if not token:
            raise SystemExit('The admin setup code is empty. Restart the server to generate a new one.')
        url='http://127.0.0.1:8000/setup?'+urlencode({'token':token})
        message='Opened the one-time admin setup page. Choose your own password in the browser.'
    else:
        with db.connect() as connection:
            users_table=connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
            admin_exists=bool(connection.execute("SELECT 1 FROM users WHERE role='admin'").fetchone()) if users_table else False
        if not admin_exists:
            raise SystemExit('Admin setup is not ready. Start the server, wait for it to initialize, then run this again.')
        url='http://127.0.0.1:8000/login'
        message='An admin account is already set up. Opened the login page.'
    webbrowser.open(url)
    print(message)

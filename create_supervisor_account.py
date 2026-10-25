"""Create the first supervisor locally; never reset an existing account.

The random password is shown once and is never written to a source or log file.
Run only on the server machine as its owner.
"""
import json
import secrets
import auth
import db


def create():
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM users WHERE role='supervisor' AND enabled=1").fetchone():
            raise SystemExit('Supervisor already configured. No account or password changed.')
        username='supervisor'
        if c.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone():
            raise SystemExit('Username already exists. No account or password changed.')
        password=secrets.token_urlsafe(12)
        row=c.execute('''INSERT INTO users(username,display_name,password_hash,role,created_at)
            VALUES(?,?,?,'supervisor',?)''',(username,'หัวหน้างาน',auth.password_hash(password),auth.now()))
        auth.audit(c,'user_created',row.lastrowid,'supervisor; provisioned locally at owner request')
    return {'username':username,'password':password}


if __name__=='__main__':
    print(json.dumps(create(),ensure_ascii=False))

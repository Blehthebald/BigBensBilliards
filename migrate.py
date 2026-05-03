import sqlite3
from app import app, db, Player

with app.app_context():
    # 1. Create the brand new database with all the updated tables
    db.create_all()

    # 2. Connect to the old database file directly
    conn = sqlite3.connect('old_league.db')
    cursor = conn.cursor()

    # 3. Grab all the player data INCLUDING THE PASSWORD HASH
    cursor.execute("SELECT id, name, password_hash, elo, wins, losses FROM player")
    old_players = cursor.fetchall()

    # 4. Loop through and add them to the new database
    for old_data in old_players:
        p_id, name, pwd_hash, elo, wins, losses = old_data

        # Check if they exist just to prevent duplicate errors
        if not Player.query.get(p_id):
            new_player = Player(
                id=p_id,
                name=name,
                password_hash=pwd_hash,
                elo=elo,
                wins=wins,
                losses=losses
            )
            db.session.add(new_player)

    db.session.commit()
    conn.close()
    print(f"Successfully migrated {len(old_players)} players and their passwords to the new database!")
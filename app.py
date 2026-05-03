import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_pool_key'

# --- SMART DATABASE PATH ---
# If running on PythonAnywhere, use the absolute path.
if 'PYTHONANYWHERE_DOMAIN' in os.environ:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////home/Blehthebald/mysite/league.db'
# If running locally on your computer, use a simple local path.
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///league.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# SECURITY FIX 2: Use an environment variable for the Admin Password.
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# --- DATABASE MODELS ---
class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    elo = db.Column(db.Integer, default=800)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)


class Season(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=False)


class SeasonRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, nullable=True)
    player_name = db.Column(db.String(50), nullable=False)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=False)
    final_elo = db.Column(db.Integer, default=800)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    season = db.relationship('Season')


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_type = db.Column(db.String(10), default='1v1')
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=True)

    p1_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    p2_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    p1_partner_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    p2_partner_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)

    # NEW: Historical Snapshots of Elo exactly when the match occurred
    p1_elo_pre = db.Column(db.Integer, nullable=True)
    p2_elo_pre = db.Column(db.Integer, nullable=True)
    p1_partner_elo_pre = db.Column(db.Integer, nullable=True)
    p2_partner_elo_pre = db.Column(db.Integer, nullable=True)

    winner_id = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='pending_opponent')

    p1 = db.relationship('Player', foreign_keys=[p1_id])
    p2 = db.relationship('Player', foreign_keys=[p2_id])
    p1_partner = db.relationship('Player', foreign_keys=[p1_partner_id])
    p2_partner = db.relationship('Player', foreign_keys=[p2_partner_id])
    season = db.relationship('Season')

class CustomAward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    icon = db.Column(db.String(10), nullable=False) # e.g., 🏆, 🤡, 🎯
    desc = db.Column(db.String(200), nullable=False)

    # This backref automatically creates a list of custom awards attached to the Player
    player = db.relationship('Player', backref=db.backref('custom_awards', lazy=True))

# --- MASTER ACHIEVEMENTS DICTIONARY ---
ACHIEVEMENTS = [
    {"id": "first_blood", "name": "First Blood", "icon": "🎱", "desc": "Win a match."},
    {"id": "veteran", "name": "Veteran", "icon": "🛡️", "desc": "Play 50 total matches."},
    {"id": "pool_shark", "name": "Pool Shark", "icon": "🦈", "desc": "Play 100 total matches."},
    {"id": "the_prodigy", "name": "The Prodigy", "icon": "🌟", "desc": "Reach a rating of 1000 Elo."},
    {"id": "grandmaster", "name": "Grandmaster", "icon": "👑", "desc": "Reach a rating of 1200 Elo."},
    {"id": "the_sniper", "name": "The Sniper", "icon": "🎯", "desc": "Win 10 matches in 1v1 format."},
    {"id": "team_player", "name": "Team Player", "icon": "🤝", "desc": "Play 10 matches in 2v2 format."},
    {"id": "dynamic_duo", "name": "Dynamic Duo", "icon": "👯", "desc": "Win 5 matches in 2v2 format."},
    {"id": "nemesis", "name": "Nemesis", "icon": "⚔️", "desc": "Play against the exact same opponent 5 times in 1v1s."},
    {"id": "giant_slayer", "name": "Giant Slayer", "icon": "🗡️",
     "desc": "Defeat an opponent whose current Elo is at least 100 points higher than yours."}
]


def calculate_achievements(player):
    """Evaluates a player's stats and returns a list of all achievements with their unlock status."""
    unlocked_ids = set()

    # 1. Broad Stat Checks
    if player.wins >= 1: unlocked_ids.add("first_blood")

    total_matches = player.wins + player.losses
    if total_matches >= 50: unlocked_ids.add("veteran")
    if total_matches >= 100: unlocked_ids.add("pool_shark")

    # 2. Deep Match Analysis (Sorted chronologically to check peak Elo)
    matches = Match.query.filter(
        (Match.p1_id == player.id) | (Match.p2_id == player.id) |
        (Match.p1_partner_id == player.id) | (Match.p2_partner_id == player.id)
    ).order_by(Match.id.asc()).all()

    sniper_wins = 0
    team_matches = 0
    team_wins = 0
    opponents_count = {}

    # Start tracking peak Elo using their current Elo as the baseline
    peak_elo = player.elo

    for m in matches:
        won = False  # Track if they won this specific match

        # Check historical snapshots to find their peak Elo
        if m.p1_id == player.id and m.p1_elo_pre is not None:
            peak_elo = max(peak_elo, m.p1_elo_pre)
        elif m.p2_id == player.id and m.p2_elo_pre is not None:
            peak_elo = max(peak_elo, m.p2_elo_pre)
        elif m.p1_partner_id == player.id and m.p1_partner_elo_pre is not None:
            peak_elo = max(peak_elo, m.p1_partner_elo_pre)
        elif m.p2_partner_id == player.id and m.p2_partner_elo_pre is not None:
            peak_elo = max(peak_elo, m.p2_partner_elo_pre)

        # Evaluate 1v1 Matches
        if m.match_type == '1v1':
            is_p1 = (m.p1_id == player.id)
            won = (m.winner_id == player.id)
            opponent = m.p2 if is_p1 else m.p1

            if opponent:
                # Track Nemesis
                opponents_count[opponent.id] = opponents_count.get(opponent.id, 0) + 1
                if opponents_count[opponent.id] >= 5:
                    unlocked_ids.add("nemesis")

                # Track Sniper & Giant Slayer
                if won:
                    sniper_wins += 1
                    if opponent.elo >= (player.elo + 100):
                        unlocked_ids.add("giant_slayer")

        # Evaluate 2v2 Matches
        elif m.match_type == '2v2':
            team_matches += 1
            if (m.winner_id == m.p1_id and (m.p1_id == player.id or m.p1_partner_id == player.id)) or \
                    (m.winner_id == m.p2_id and (m.p2_id == player.id or m.p2_partner_id == player.id)):
                team_wins += 1

    # Apply Match-Based Unlocks
    if sniper_wins >= 10: unlocked_ids.add("the_sniper")
    if team_matches >= 10: unlocked_ids.add("team_player")
    if team_wins >= 5: unlocked_ids.add("dynamic_duo")

    # Apply Peak Elo Unlocks
    if peak_elo >= 1000: unlocked_ids.add("the_prodigy")
    if peak_elo >= 1200: unlocked_ids.add("grandmaster")

    # Build the final list with lock/unlock status
    player_achievements = []
    for ach in ACHIEVEMENTS:
        ach_copy = ach.copy()
        ach_copy['unlocked'] = (ach['id'] in unlocked_ids)
        player_achievements.append(ach_copy)

    return player_achievements

# --- ELO MATH LOGIC ---
def probwin(player_elo, other_player_elo):
    return 1 / (1 + 10 ** ((other_player_elo - player_elo) / 400))


def elo_change(player_elo, outcome, prob_of_win):
    return player_elo + 32 * (outcome - prob_of_win)


# --- ERROR HANDLERS ---
@app.errorhandler(404)
def page_not_found(e):
    # The '404' at the end tells the browser it is officially a "Not Found" response
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    # It's crucial to rollback the database session on a 500 error
    # so a failed database action doesn't lock up your app permanently.
    db.session.rollback()
    return render_template('500.html'), 500

# --- GLOBAL ROUTES ---
@app.route('/')
def index():
    seasons = Season.query.all()
    selected_season_id = request.args.get('season_id')
    active_season = Season.query.filter_by(is_active=True).first()

    if not selected_season_id or (active_season and str(selected_season_id) == str(active_season.id)):
        records = Player.query.order_by(Player.elo.desc()).all()
        players_data = [{'id': r.id, 'name': r.name, 'elo': r.elo, 'wins': r.wins, 'losses': r.losses} for r in records]
        display_season = active_season.name if active_season else "Current Season"
        is_archived = False
    else:
        selected = Season.query.get(selected_season_id)
        records = SeasonRecord.query.filter_by(season_id=selected_season_id).order_by(
            SeasonRecord.final_elo.desc()).all()
        players_data = [
            {'id': r.player_id, 'name': r.player_name, 'elo': r.final_elo, 'wins': r.wins, 'losses': r.losses} for r in
            records]
        display_season = selected.name
        is_archived = True

    most_wins = max(players_data, key=lambda x: x['wins']) if players_data else None
    most_active = max(players_data, key=lambda x: (x['wins'] + x['losses'])) if players_data else None

    return render_template('index.html', players=players_data, seasons=seasons,
                           display_season=display_season, is_archived=is_archived,
                           most_wins=most_wins, most_active=most_active)


@app.route('/profile/<int:player_id>')
def profile(player_id):
    player = Player.query.get_or_404(player_id)
    matches = Match.query.filter(
        (Match.p1_id == player_id) | (Match.p2_id == player_id) |
        (Match.p1_partner_id == player_id) | (Match.p2_partner_id == player_id)
    ).order_by(Match.id.desc()).all()

    total = player.wins + player.losses
    win_pct = round((player.wins / total * 100), 1) if total > 0 else 0

    # Calculate dynamic achievements
    achievements = calculate_achievements(player)

    # Simplified Rivals Logic (Count games where they were directly p1 vs p2)
    rivals_data = {}
    for m in matches:
        if m.match_type == '1v1':
            opp_id = m.p2_id if m.p1_id == player_id else m.p1_id
            opp = Player.query.get(opp_id)
            if opp:
                if opp.name not in rivals_data:
                    rivals_data[opp.name] = {'total': 0, 'wins': 0, 'losses': 0}
                rivals_data[opp.name]['total'] += 1
                if m.winner_id == player_id:
                    rivals_data[opp.name]['wins'] += 1
                else:
                    rivals_data[opp.name]['losses'] += 1

    rivals = [{'name': k, **v} for k, v in rivals_data.items()]
    rivals.sort(key=lambda x: x['total'], reverse=True)

    return render_template('profile.html', player=player, total=total, win_pct=win_pct, matches=matches,
                           rivals=rivals[:5], achievements=achievements)


@app.route('/achievements')
def achievements_page():
    # Pass the global master list directly to the template
    return render_template('achievements.html', achievements=ACHIEVEMENTS)


@app.route('/history')
def history():
    matches = Match.query.filter_by(status='approved').order_by(Match.id.desc()).all()
    return render_template('history.html', matches=matches)


# --- AUTHENTICATION ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name'].strip()
        password = request.form['password']
        if name.lower() == 'admin': return redirect(url_for('signup'))
        if Player.query.filter_by(name=name).first(): return redirect(url_for('signup'))
        hashed_pw = generate_password_hash(password)
        db.session.add(Player(name=name, password_hash=hashed_pw))
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']

        # --- ADMIN LOGIN CHECK ---
        if name == 'admin':
            if password == ADMIN_PASSWORD:
                session['admin'] = True
                flash("Welcome back, Admin!", "success")
                return redirect(url_for('admin'))
            else:
                flash("Incorrect admin password.", "error")
                return redirect(url_for('login'))

        # --- NORMAL PLAYER LOGIN CHECK ---
        player = Player.query.filter_by(name=name).first()
        if player and check_password_hash(player.password_hash, password):
            session['player_id'] = player.id
            flash("Logged in successfully.", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password.", "error")

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# --- DASHBOARD ---
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'player_id' not in session: return redirect(url_for('login'))
    player_id = session['player_id']
    active_season = Season.query.filter_by(is_active=True).first()

    if request.method == 'POST':
        match_type = request.form['match_type']
        p2_id = int(request.form['p2_id'])
        outcome = request.form['outcome']

        new_match = Match(p1_id=player_id, p2_id=p2_id, match_type=match_type, status='pending_opponent')
        if active_season: new_match.season_id = active_season.id

        if match_type == '2v2':
            p1_partner_id = int(request.form['p1_partner_id'])
            p2_partner_id = int(request.form['p2_partner_id'])
            players_in_match = {player_id, p2_id, p1_partner_id, p2_partner_id}
            if len(players_in_match) < 4: return redirect(url_for('dashboard'))
            new_match.p1_partner_id = p1_partner_id
            new_match.p2_partner_id = p2_partner_id

        elif player_id == p2_id:
            return redirect(url_for('dashboard'))

        if outcome == 'team1_won':
            new_match.winner_id = player_id
        elif outcome == 'team2_won':
            new_match.winner_id = p2_id

        db.session.add(new_match)
        db.session.commit()
        return redirect(url_for('dashboard'))

    pending_for_me = Match.query.filter_by(p2_id=player_id, status='pending_opponent').all()
    opponents = Player.query.filter(Player.id != player_id).order_by(Player.name).all()
    return render_template('dashboard.html', opponents=opponents, pending_for_me=pending_for_me)


@app.route('/player/confirm/<int:match_id>')
def player_confirm(match_id):
    if 'player_id' not in session: return redirect(url_for('login'))
    match = Match.query.get(match_id)
    if match and match.p2_id == session['player_id'] and match.status == 'pending_opponent':
        match.status = 'pending_admin'
        db.session.commit()
    return redirect(url_for('dashboard'))


@app.route('/player/reject/<int:match_id>')
def player_reject(match_id):
    if 'player_id' not in session: return redirect(url_for('login'))
    match = Match.query.get(match_id)
    if match and (match.p2_id == session['player_id'] or match.p1_id == session['player_id']):
        db.session.delete(match)
        db.session.commit()
    return redirect(url_for('dashboard'))


# --- ADMIN ROUTES ---
@app.route('/admin')
def admin():
    if 'admin' not in session: return redirect(url_for('login'))
    pending_matches = Match.query.filter_by(status='pending_admin').all()
    players = Player.query.order_by(Player.name).all()
    active_season = Season.query.filter_by(is_active=True).first()
    awards = CustomAward.query.all()

    # NEW: Fetch all seasons so we can list them in the rename dropdown
    all_seasons = Season.query.order_by(Season.id.desc()).all()

    return render_template('admin.html', matches=pending_matches, players=players,
                           active_season=active_season, awards=awards, all_seasons=all_seasons)


@app.route('/admin/approve/<int:match_id>')
def admin_approve(match_id):
    if 'admin' not in session: return redirect(url_for('login'))
    match = Match.query.get(match_id)
    if match and match.status == 'pending_admin':
        # NEW: Snapshot Elo BEFORE math is applied for Giant Slayer logic
        match.p1_elo_pre = match.p1.elo
        match.p2_elo_pre = match.p2.elo

        t1_out = 1 if match.winner_id == match.p1_id else 0
        t2_out = 1 if match.winner_id == match.p2_id else 0

        if match.match_type == '1v1':
            p1, p2 = match.p1, match.p2
            p1.wins += t1_out;
            p1.losses += t2_out
            p2.wins += t2_out;
            p2.losses += t1_out
            prob1, prob2 = probwin(p1.elo, p2.elo), probwin(p2.elo, p1.elo)
            p1.elo = int(round(elo_change(p1.elo, t1_out, prob1)))
            p2.elo = int(round(elo_change(p2.elo, t2_out, prob2)))

        elif match.match_type == '2v2':
            p1, p1_p = match.p1, match.p1_partner
            p2, p2_p = match.p2, match.p2_partner

            # Snapshot partner elos
            match.p1_partner_elo_pre = p1_p.elo
            match.p2_partner_elo_pre = p2_p.elo

            t1_elo = p1.elo + p1_p.elo;
            t2_elo = p2.elo + p2_p.elo
            prob1, prob2 = probwin(t1_elo, t2_elo), probwin(t2_elo, t1_elo)
            delta1 = elo_change(t1_elo, t1_out, prob1) - t1_elo
            delta2 = elo_change(t2_elo, t2_out, prob2) - t2_elo

            for player in [p1, p1_p]: player.elo += int(round(delta1)); player.wins += t1_out; player.losses += t2_out
            for player in [p2, p2_p]: player.elo += int(round(delta2)); player.wins += t2_out; player.losses += t1_out

        match.status = 'approved'
        db.session.commit()
    return redirect(url_for('admin'))


@app.route('/admin/reject/<int:match_id>')
def admin_reject(match_id):
    if 'admin' not in session: return redirect(url_for('login'))
    match = Match.query.get(match_id)
    if match: db.session.delete(match); db.session.commit()
    return redirect(url_for('admin'))


@app.route('/admin/end_season', methods=['POST'])
def admin_end_season():
    if 'admin' not in session: return redirect(url_for('login'))

    new_season_name = request.form['new_season_name']
    active_season = Season.query.filter_by(is_active=True).first()

    if active_season:
        players = Player.query.all()
        for p in players:
            record = SeasonRecord(player_id=p.id, player_name=p.name, season_id=active_season.id, final_elo=p.elo,
                                  wins=p.wins, losses=p.losses)
            db.session.add(record)
            p.elo = 800
            p.wins = 0
            p.losses = 0
        active_season.is_active = False

    new_s = Season(name=new_season_name, is_active=True)
    db.session.add(new_s)
    db.session.commit()
    flash(f"Season Ended! Welcome to {new_season_name}.")
    return redirect(url_for('admin'))


@app.route('/admin/edit_elo', methods=['POST'])
def admin_edit_elo():
    if 'admin' not in session: return redirect(url_for('login'))
    player = Player.query.get(request.form['player_id'])
    if player:
        player.elo = int(request.form['new_elo'])
        db.session.commit()
    return redirect(url_for('admin'))


@app.route('/admin/remove_player', methods=['POST'])
def admin_remove_player():
    if 'admin' not in session: return redirect(url_for('login'))
    player = Player.query.get(request.form['player_id'])
    if player:
        Match.query.filter(
            (Match.p1_id == player.id) | (Match.p2_id == player.id) |
            (Match.p1_partner_id == player.id) | (Match.p2_partner_id == player.id)
        ).delete()
        db.session.delete(player)
        db.session.commit()
    return redirect(url_for('admin'))


@app.route('/admin/force_match', methods=['POST'])
def admin_force_match():
    if 'admin' not in session: return redirect(url_for('login'))

    match_type = request.form['match_type']
    p1_id = int(request.form['p1_id'])
    p2_id = int(request.form['p2_id'])
    outcome = request.form['outcome']
    active_season = Season.query.filter_by(is_active=True).first()

    new_match = Match(p1_id=p1_id, p2_id=p2_id, match_type=match_type, status='pending_admin')
    if active_season: new_match.season_id = active_season.id

    if match_type == '2v2':
        p1_partner_id = int(request.form['p1_partner_id'])
        p2_partner_id = int(request.form['p2_partner_id'])
        if len({p1_id, p2_id, p1_partner_id, p2_partner_id}) < 4: return redirect(url_for('admin'))
        new_match.p1_partner_id = p1_partner_id
        new_match.p2_partner_id = p2_partner_id
    elif p1_id == p2_id:
        return redirect(url_for('admin'))

    if outcome == 'team1_won':
        new_match.winner_id = p1_id
    elif outcome == 'team2_won':
        new_match.winner_id = p2_id

    db.session.add(new_match)
    db.session.commit()
    return redirect(url_for('admin_approve', match_id=new_match.id))


@app.route('/admin/grant_award', methods=['POST'])
def admin_grant_award():
    if 'admin' not in session: return redirect(url_for('login'))

    player_id = int(request.form['player_id'])
    name = request.form['award_name']
    icon = request.form['award_icon']
    desc = request.form['award_desc']

    new_award = CustomAward(player_id=player_id, name=name, icon=icon, desc=desc)
    db.session.add(new_award)
    db.session.commit()

    flash(f"Custom award '{name}' granted!")
    return redirect(url_for('admin'))


@app.route('/admin/revoke_award/<int:award_id>')
def admin_revoke_award(award_id):
    if 'admin' not in session: return redirect(url_for('login'))
    award = CustomAward.query.get(award_id)
    if award:
        db.session.delete(award)
        db.session.commit()
        flash("Custom award revoked.")
    return redirect(url_for('admin'))


@app.route('/admin/rename_season', methods=['POST'])
def admin_rename_season():
    if 'admin' not in session: return redirect(url_for('login'))

    season_id = request.form.get('season_id')
    new_name = request.form.get('new_name')

    if season_id and new_name:
        season = Season.query.get(season_id)
        if season:
            old_name = season.name
            season.name = new_name.strip()
            db.session.commit()
            flash(f"Season renamed from '{old_name}' to '{season.name}'.", "success")

    return redirect(url_for('admin'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Season.query.first():
            db.session.add(Season(name="2026-2027 Term 1 Part A", is_active=True))
            db.session.commit()
    app.run(debug=True)
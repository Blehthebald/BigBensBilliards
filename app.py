import os
from sqlalchemy import or_
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_pool_key'

# --- SMART DATABASE PATH ---
# Use the DATABASE_URL environment variable if it exists (on Vercel/Supabase), otherwise fall back to local SQLite
db_url = os.environ.get('DATABASE_URL', 'sqlite:///league.db')

# SQLAlchemy requires the URL to start with 'postgresql://' instead of 'postgres://'
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# SECURITY FIX: Use an environment variable for the Super Admin (You)
SUPER_ADMIN_PASSWORD = os.environ.get('SUPER_ADMIN_PASSWORD', 'godmode123')


# --- DATABASE MODELS ---
class League(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url_slug = db.Column(db.String(50), unique=True, nullable=False)  # e.g., 'garden-pool'
    display_name = db.Column(db.String(100), nullable=False)  # e.g., 'Garden International'
    admin_password_hash = db.Column(db.String(200), nullable=False)

    players = db.relationship('Player', backref='league', lazy=True)
    seasons = db.relationship('Season', backref='league', lazy=True)
    matches = db.relationship('Match', backref='league', lazy=True)
    season_records = db.relationship('SeasonRecord', backref='league', lazy=True)
    custom_awards = db.relationship('CustomAward', backref='league', lazy=True)




class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, db.ForeignKey('league.id'), nullable=False)
    is_approved = db.Column(db.Boolean, default=False)

    name = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    elo = db.Column(db.Integer, default=800)
    peak_elo = db.Column(db.Integer, default=800)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)


class Season(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, db.ForeignKey('league.id'), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=False)


class SeasonRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, db.ForeignKey('league.id'), nullable=False)

    player_id = db.Column(db.Integer, nullable=True)
    player_name = db.Column(db.String(50), nullable=False)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=False)
    final_elo = db.Column(db.Integer, default=800)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    season = db.relationship('Season')


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, db.ForeignKey('league.id'), nullable=False)

    match_type = db.Column(db.String(10), default='1v1')
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=True)

    p1_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    p2_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    p1_partner_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    p2_partner_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)

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
    league_id = db.Column(db.Integer, db.ForeignKey('league.id'), nullable=False)

    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    icon = db.Column(db.String(10), nullable=False)
    desc = db.Column(db.String(200), nullable=False)

    player = db.relationship('Player', backref=db.backref('custom_awards', lazy=True))


# Ensure tables are created
with app.app_context():
    db.create_all()
# --- GLOBAL LANDING PAGE ---
# --- GLOBAL LANDING PAGE ---
@app.route('/')
def global_home():
    # Fetch all registered leagues from the database
    leagues = League.query.all()

    # Pass the list of leagues to the landing page template
    return render_template('landing_page.html', leagues=leagues)


# --- ACHIEVEMENTS LOGIC ---
# --- ACHIEVEMENTS LOGIC ---

ACHIEVEMENTS = [
    {'id': 'first_blood', 'name': 'First Blood', 'icon': '🩸', 'desc': 'Win a match.'},
    {'id': 'veteran', 'name': 'Veteran', 'icon': '🎖️', 'desc': 'Play 50 total matches.'},
    {'id': 'pool_shark', 'name': 'Pool Shark', 'icon': '🦈', 'desc': 'Play 100 total matches.'},
    {'id': 'prodigy', 'name': 'The Prodigy', 'icon': '🌟', 'desc': 'Reach a rating of 1000 elo.'},
    {'id': 'grandmaster', 'name': 'Grandmaster', 'icon': '👑', 'desc': 'Reach a rating of 1200 elo.'},
    {'id': 'sniper', 'name': 'The Sniper', 'icon': '🎯', 'desc': 'Win 10 matches in 1v1 format.'},
    {'id': 'team_player', 'name': 'Team Player', 'icon': '🤝', 'desc': 'Play 10 matches in 2v2 format.'},
    {'id': 'dynamic_duo', 'name': 'Dynamic Duo', 'icon': '👯', 'desc': 'Win 5 matches in 2v2 format.'},
    {'id': 'my_brother', 'name': 'My Brother', 'icon': '⚔️', 'desc': 'Win 20 matches in 2v2 format.'},
    {'id': 'nemesis', 'name': 'Nemesis', 'icon': '🦹', 'desc': 'Play against the exact same opponent 5 times in 1v1s.'},
    {'id': 'giant_slayer', 'name': 'Giant Slayer', 'icon': '🗡️',
     'desc': 'Defeat an opponent whose current Elo is at least 150 points higher than yours.'},
    {'id': 'jackpot', 'name': 'Jackpot', 'icon': '🎰', 'desc': 'Win 10 games in a row.'},
    {'id': 'the_king', 'name': 'The King', 'icon': '👑', 'desc': 'End a season as the top ranked player.'},
    {'id': 'podium_finish', 'name': 'Podium Finish', 'icon': '🏆',
     'desc': 'End a season as one of the top three ranked players.'},
    {'id': 'honored_one', 'name': 'The Honored One', 'icon': '🐐 ', 'desc': 'End 5 seasons as the top ranked player.'}
]


def calculate_achievements(player):
    """Calculates which global achievements a player has unlocked."""
    earned = []

    # --- 1. BASIC STATS ---
    total_matches = player.wins + player.losses

    # THE FIX: Always take the highest value between their current Elo and their peak_elo column.
    # This completely solves the issue where older players were defaulted to an 800 peak.
    current_peak = player.peak_elo if player.peak_elo is not None else 800
    peak = max(player.elo, current_peak)

    if player.wins >= 1: earned.append(ACHIEVEMENTS[0])
    if total_matches >= 50: earned.append(ACHIEVEMENTS[1])
    if total_matches >= 100: earned.append(ACHIEVEMENTS[2])
    if peak >= 1000: earned.append(ACHIEVEMENTS[3])
    if peak >= 1200: earned.append(ACHIEVEMENTS[4])

    # --- 2. MATCH HISTORY TRACKING ---
    matches = Match.query.filter(
        ((Match.p1_id == player.id) | (Match.p2_id == player.id) |
         (Match.p1_partner_id == player.id) | (Match.p2_partner_id == player.id)),
        Match.status == 'approved',
        Match.league_id == player.league_id
    ).order_by(Match.id.asc()).all()

    wins_1v1 = 0
    played_2v2 = 0
    wins_2v2 = 0
    opponents_1v1 = {}
    current_streak = 0
    max_streak = 0
    giant_slayer_unlocked = False

    for m in matches:
        is_1v1 = (m.match_type == '1v1')
        is_2v2 = (m.match_type == '2v2')

        # Determine if player was on Team 1
        is_team_1 = (player.id == m.p1_id or player.id == m.p1_partner_id)
        team_1_won = (m.winner_id == m.p1_id)

        # Did the player win this specific match?
        won_match = (is_team_1 and team_1_won) or (not is_team_1 and not team_1_won)

        if won_match:
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak

            if is_1v1:
                wins_1v1 += 1
                # Check for Giant Slayer
                opponent_id = m.p2_id if is_team_1 else m.p1_id
                opponent = Player.query.get(opponent_id)
                if opponent and (opponent.elo - player.elo) >= 150:
                    giant_slayer_unlocked = True
            elif is_2v2:
                wins_2v2 += 1
        else:
            current_streak = 0  # Streak broken

        if is_2v2:
            played_2v2 += 1

        if is_1v1:
            # Track opponents for Nemesis
            opponent_id = m.p2_id if is_team_1 else m.p1_id
            opponents_1v1[opponent_id] = opponents_1v1.get(opponent_id, 0) + 1

    if wins_1v1 >= 10: earned.append(ACHIEVEMENTS[5])  # The Sniper
    if played_2v2 >= 10: earned.append(ACHIEVEMENTS[6])  # Team Player
    if wins_2v2 >= 5: earned.append(ACHIEVEMENTS[7])  # Dynamic Duo
    if wins_2v2 >= 20: earned.append(ACHIEVEMENTS[8])  # My Brother
    if any(count >= 5 for count in opponents_1v1.values()):
        earned.append(ACHIEVEMENTS[9])  # Nemesis
    if giant_slayer_unlocked: earned.append(ACHIEVEMENTS[10])  # Giant Slayer
    if max_streak >= 10: earned.append(ACHIEVEMENTS[11])  # Jackpot

    # --- 3. ARCHIVED SEASON RECORDS ---
    past_seasons = Season.query.filter_by(league_id=player.league_id, is_active=False).all()
    top_1_count = 0
    top_3_count = 0

    for season in past_seasons:
        # Fetch only the top 3 players from that specific archived season
        top_records = SeasonRecord.query.filter_by(season_id=season.id).order_by(SeasonRecord.final_elo.desc()).limit(
            3).all()
        for index, record in enumerate(top_records):
            if record.player_id == player.id:
                if index == 0:
                    top_1_count += 1
                top_3_count += 1
                break  # Found the player, move to next season

    if top_1_count >= 1: earned.append(ACHIEVEMENTS[12])  # The King
    if top_3_count >= 1: earned.append(ACHIEVEMENTS[13])  # Podium Finish
    if top_1_count >= 5: earned.append(ACHIEVEMENTS[14])  # The Honored One

    if top_1_count >= 1: earned.append(ACHIEVEMENTS[12])  # The King
    if top_3_count >= 1: earned.append(ACHIEVEMENTS[13])  # Podium Finish
    if top_1_count >= 5: earned.append(ACHIEVEMENTS[14])  # The Honored One

    # --- FORMAT FOR THE HTML TEMPLATE ---
    # Convert the earned list into a full list of 15 achievements with True/False 'unlocked' flags
    earned_ids = [a['id'] for a in earned]

    final_achievements = []
    for a in ACHIEVEMENTS:
        ach_copy = a.copy()
        ach_copy['unlocked'] = (a['id'] in earned_ids)
        final_achievements.append(ach_copy)

    return final_achievements


# --- ELO CALCULATION LOGIC ---
def update_elos(match):
    """Calculates and updates Elos for players in an approved match."""

    # 1. Fetch the actual player objects
    p1 = Player.query.get(match.p1_id)
    p2 = Player.query.get(match.p2_id)

    team1_players = [p1]
    team2_players = [p2]

    # Check if it's a 2v2 and append partners to the teams
    p1_partner = None
    p2_partner = None
    if match.match_type == '2v2':
        if match.p1_partner_id:
            p1_partner = Player.query.get(match.p1_partner_id)
            team1_players.append(p1_partner)
        if match.p2_partner_id:
            p2_partner = Player.query.get(match.p2_partner_id)
            team2_players.append(p2_partner)

    # ---> THE FIX: SAVE ELOS BEFORE THEY CHANGE <---
    match.p1_elo_pre = p1.elo
    match.p2_elo_pre = p2.elo
    if match.match_type == '2v2':
        if p1_partner: match.p1_partner_elo_pre = p1_partner.elo
        if p2_partner: match.p2_partner_elo_pre = p2_partner.elo

    # 2. Calculate Team Averages
    team1_avg_elo = sum(p.elo for p in team1_players) / len(team1_players)
    team2_avg_elo = sum(p.elo for p in team2_players) / len(team2_players)

    # 3. Calculate Expected Win Probabilities
    expected_team1 = 1 / (1 + 10 ** ((team2_avg_elo - team1_avg_elo) / 400))
    expected_team2 = 1 / (1 + 10 ** ((team1_avg_elo - team2_avg_elo) / 400))

    # 4. Determine Actual Outcomes
    team1_won = (match.winner_id == match.p1_id)
    actual_team1 = 1 if team1_won else 0
    actual_team2 = 0 if team1_won else 1

    # 5. Calculate Elo Change (Standard K-Factor of 32)
    K = 32
    elo_change_team1 = round(K * (actual_team1 - expected_team1))
    elo_change_team2 = round(K * (actual_team2 - expected_team2))

    # 6. Apply Elo Changes, Track Peaks, and Update Win/Loss Stats
    for p in team1_players:
        current_peak = p.peak_elo if p.peak_elo is not None else 800
        p.peak_elo = max(p.elo, current_peak)

        p.elo += elo_change_team1
        if p.elo > p.peak_elo: p.peak_elo = p.elo

        if team1_won: p.wins += 1
        else: p.losses += 1

    for p in team2_players:
        current_peak = p.peak_elo if p.peak_elo is not None else 800
        p.peak_elo = max(p.elo, current_peak)

        p.elo += elo_change_team2
        if p.elo > p.peak_elo: p.peak_elo = p.elo

        if not team1_won: p.wins += 1
        else: p.losses += 1

    # Save all the updated stats to the database
    db.session.commit()
# --- SUPER ADMIN (GOD MODE) ROUTES ---
@app.route('/god-mode-portal', methods=['GET', 'POST'])
def super_admin():
    if not session.get('is_super_admin'):
        if request.method == 'POST':
            password = request.form.get('password')
            if password == SUPER_ADMIN_PASSWORD:
                session['is_super_admin'] = True
                flash("God Mode Activated.", "success")
                return redirect(url_for('super_admin'))
            else:
                flash("Invalid master password.", "error")
        return render_template('super_admin_login.html')

    if request.method == 'POST':
        display_name = request.form.get('display_name')
        url_slug = request.form.get('url_slug')
        temp_password = request.form.get('temp_password')

        if League.query.filter_by(url_slug=url_slug).first():
            flash(f"Error: The URL slug '{url_slug}' is already taken.", "error")
        elif display_name and url_slug and temp_password:
            hashed_pw = generate_password_hash(temp_password)
            new_league = League(display_name=display_name, url_slug=url_slug, admin_password_hash=hashed_pw)
            db.session.add(new_league)
            db.session.commit()
            flash(f"League '{display_name}' created! Slug: /{url_slug}", "success")

        return redirect(url_for('super_admin'))

    leagues = League.query.all()
    return render_template('super_admin_dashboard.html', leagues=leagues)


@app.route('/god-mode-logout')
def super_admin_logout():
    session.pop('is_super_admin', None)
    return redirect(url_for('super_admin'))


# --- AUTHENTICATION ---
@app.route('/<league_slug>/signup', methods=['GET', 'POST'])
def signup(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    if request.method == 'POST':
        name = request.form['name'].strip()
        password = request.form['password']
        confirm_password = request.form.get('confirm_password')

        # NEW: Check if passwords match
        if password != confirm_password:
            flash("Passwords do not match! Please try again.", "error")
            return redirect(url_for('signup', league_slug=league.url_slug))

        if name.lower() == 'admin':
            flash("The username 'admin' is reserved.", "error")
            return redirect(url_for('signup', league_slug=league.url_slug))

        if Player.query.filter_by(name=name, league_id=league.id).first():
            flash("That username is already taken. Please choose another.", "error")
            return redirect(url_for('signup', league_slug=league.url_slug))

        hashed_pw = generate_password_hash(password)
        new_player = Player(name=name, password_hash=hashed_pw, league_id=league.id, is_approved=False)
        db.session.add(new_player)
        db.session.commit()

        flash("Account created! Please wait for your league admin to approve you.", "success")
        return redirect(url_for('login', league_slug=league.url_slug))

    return render_template('signup.html', league=league)


@app.route('/<league_slug>/login', methods=['GET', 'POST'])
def login(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']

        if name == 'admin':
            if check_password_hash(league.admin_password_hash, password):
                session['admin_league_id'] = league.id
                flash(f"Welcome back, Admin of {league.display_name}!", "success")
                return redirect(url_for('admin', league_slug=league.url_slug))
            else:
                flash("Incorrect admin password.", "error")
                return redirect(url_for('login', league_slug=league.url_slug))

        player = Player.query.filter_by(name=name, league_id=league.id).first()

        if player and check_password_hash(player.password_hash, password):
            if not player.is_approved:
                flash("Your account is still pending admin approval.", "error")
                return redirect(url_for('login', league_slug=league.url_slug))

            session['player_id'] = player.id
            session['league_id'] = league.id
            flash("Logged in successfully.", "success")
            return redirect(url_for('dashboard', league_slug=league.url_slug))
        else:
            flash("Invalid username or password.", "error")

    return render_template('login.html', league=league)


@app.route('/<league_slug>/logout')
def logout(league_slug):
    session.pop('player_id', None)
    session.pop('league_id', None)
    session.pop('admin_league_id', None)
    return redirect(url_for('index', league_slug=league_slug))




@app.route('/<league_slug>/')
def index(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    # Get all seasons for this specific league to populate the dropdown
    seasons = Season.query.filter_by(league_id=league.id).order_by(Season.id.desc()).all()

    season_id = request.args.get('season_id')

    is_archived = False
    display_season = "Global Leaderboard"
    most_wins = None
    most_active = None

    # 1. Figure out WHICH season we are trying to look at
    target_season = None
    if season_id:
        target_season = Season.query.filter_by(id=season_id, league_id=league.id).first_or_404()
    else:
        # Default to the active season if no ID is in the URL
        target_season = Season.query.filter_by(league_id=league.id, is_active=True).first()

    # 2. Fetch the correct data based on if the target season is active or archived
    if target_season:
        display_season = target_season.name

        if target_season.is_active:
            # --- VIEWING THE CURRENT ACTIVE SEASON ---
            players = Player.query.filter_by(league_id=league.id).order_by(Player.elo.desc()).all()
        else:
            # --- VIEWING A PAST ARCHIVED SEASON ---
            is_archived = True
            records = SeasonRecord.query.filter_by(season_id=target_season.id).order_by(
                SeasonRecord.final_elo.desc()).all()

            # Package the records into a dictionary to match the Player object structure
            players = []
            for r in records:
                players.append({
                    'id': r.player_id,
                    'name': r.player_name,
                    'elo': r.final_elo,
                    'wins': r.wins,
                    'losses': r.losses
                })
    else:
        # Fallback just in case no seasons exist at all yet
        players = Player.query.filter_by(league_id=league.id).order_by(Player.elo.desc()).all()

    # 3. Calculate "Most Wins" and "Most Active" badges
    if players:
        # Support both dictionary (archived) and object (current) attribute access
        def get_wins(p):
            return p['wins'] if isinstance(p, dict) else p.wins

        def get_total(p):
            return (p['wins'] + p['losses']) if isinstance(p, dict) else (p.wins + p.losses)

        most_wins = max(players, key=get_wins)
        most_active = max(players, key=get_total)

        # Don't show badges if nobody has played any games yet
        if get_wins(most_wins) == 0:
            most_wins = None
            most_active = None

    return render_template('index.html', league=league, players=players, seasons=seasons,
                           display_season=display_season, is_archived=is_archived,
                           most_wins=most_wins, most_active=most_active)


@app.route('/<league_slug>/dashboard', methods=['GET', 'POST'])
def dashboard(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    if 'player_id' not in session or session.get('league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    if request.method == 'POST':
        match_type = request.form.get('match_type')
        p2_id = request.form.get('p2_id')
        outcome = request.form.get('outcome')

        if not p2_id or p2_id == str(session['player_id']):
            flash("Invalid opponent.", "error")
            return redirect(url_for('dashboard', league_slug=league.url_slug))

        match = Match(
            league_id=league.id,
            match_type=match_type,
            p1_id=session['player_id'],
            p2_id=p2_id,
            status='pending_admin'  # <-- This forces it straight to the admin dashboard!
        )

        if match_type == '2v2':
            match.p1_partner_id = request.form.get('p1_partner_id')
            match.p2_partner_id = request.form.get('p2_partner_id')

        if outcome == 'team1_won':
            match.winner_id = session['player_id']
        else:
            match.winner_id = p2_id

        db.session.add(match)
        db.session.commit()
        flash("Match logged! Awaiting final admin approval.", "success")
        return redirect(url_for('dashboard', league_slug=league.url_slug))

    # Fetch the logged-in player
    player = Player.query.get(session['player_id'])

    # Fetch opponents (Everyone in the SAME league, excluding the logged-in player)
    opponents = Player.query.filter(Player.id != player.id, Player.league_id == league.id).order_by(Player.name).all()

    # --- THE MISSING QUERY ---
    # Fetch matches awaiting the logged-in player's confirmation
    pending_for_me = Match.query.filter(
        Match.league_id == league.id,
        Match.status == 'pending_opponent',
        ((Match.p2_id == player.id) | (Match.p2_partner_id == player.id))
    ).all()

    return render_template('dashboard.html', league=league, player=player,
                           opponents=opponents, pending_for_me=pending_for_me)


@app.route('/<league_slug>/rename', methods=['POST'])
def rename_player(league_slug):
    # Get the current league
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    # Ensure the user is actually logged in as a player
    player_id = session.get('player_id')
    if not player_id:
        flash("You must be logged in to change your name.", "error")
        return redirect(url_for('login', league_slug=league.url_slug))

    player = Player.query.filter_by(id=player_id, league_id=league.id).first()
    if not player:
        return redirect(url_for('login', league_slug=league.url_slug))

    new_name = request.form.get('new_name')

    if new_name and len(new_name.strip()) > 0:
        clean_name = new_name.strip()

        # Prevent renaming to a name that already exists in this league
        existing_player = Player.query.filter_by(league_id=league.id, name=clean_name).first()
        if existing_player and existing_player.id != player.id:
            flash(f"The name '{clean_name}' is already taken!", "error")
        else:
            # Update the name and save to database
            player.name = clean_name
            db.session.commit()
            flash("Your name has been successfully updated!", "success")
    else:
        flash("Invalid name provided.", "error")

    return redirect(url_for('dashboard', league_slug=league.url_slug))


# --- MISSING GLOBAL LEAGUE ROUTES ---
@app.route('/<league_slug>/history')
def history(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()
    matches = Match.query.filter_by(league_id=league.id, status='approved').order_by(Match.id.desc()).all()
    return render_template('history.html', league=league, matches=matches)


@app.route('/<league_slug>/achievements')
def achievements(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()
    # Assuming your ACHIEVEMENTS dictionary is still at the top of your app.py
    return render_template('achievements.html', league=league, achievements=ACHIEVEMENTS)


@app.route('/<league_slug>/profile/<int:player_id>')
def profile(league_slug, player_id):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()
    player = Player.query.filter_by(id=player_id, league_id=league.id).first_or_404()

    total = player.wins + player.losses
    win_pct = round((player.wins / total * 100), 1) if total > 0 else 0

    matches = Match.query.filter(
        Match.league_id == league.id, Match.status == 'approved',
        ((Match.p1_id == player.id) | (Match.p2_id == player.id) |
         (Match.p1_partner_id == player.id) | (Match.p2_partner_id == player.id))
    ).order_by(Match.id.desc()).all()

    # Calculate Rivals
    rivals_dict = {}
    for m in matches:
        if m.match_type == '1v1':
            opponent = m.p2 if m.p1_id == player.id else m.p1
            won = (m.winner_id == player.id)
            if opponent:
                if opponent.id not in rivals_dict:
                    rivals_dict[opponent.id] = {'name': opponent.name, 'wins': 0, 'losses': 0, 'total': 0}
                rivals_dict[opponent.id]['total'] += 1
                if won:
                    rivals_dict[opponent.id]['wins'] += 1
                else:
                    rivals_dict[opponent.id]['losses'] += 1

    rivals = sorted(rivals_dict.values(), key=lambda x: x['total'], reverse=True)[:5]

    # --- THE MISSING TROPHY LOGIC ---
    # Fetch all CustomAwards given to this player by the Admin
    custom_awards = CustomAward.query.filter_by(player_id=player.id, league_id=league.id).all()

    # Needs your calculate_achievements function to still be in app.py!
    player_achievements = calculate_achievements(player) if 'calculate_achievements' in globals() else []

    # Make sure custom_awards is passed to the HTML template here!
    # Make sure custom_awards is passed to the HTML template here!
    return render_template('profile.html', league=league, player=player, total=total, win_pct=win_pct, matches=matches,
                           rivals=rivals, custom_awards=custom_awards, achievements=player_achievements)


# --- DASHBOARD CONFIRMATION ACTIONS ---

# --- LEAGUE ADMIN ROUTES ---
@app.route('/<league_slug>/admin')
def admin(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    if session.get('admin_league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    pending_players = Player.query.filter_by(league_id=league.id, is_approved=False).all()
    approved_players = Player.query.filter_by(league_id=league.id, is_approved=True).all()
    seasons = Season.query.filter_by(league_id=league.id).all()

    pending_matches = Match.query.filter_by(league_id=league.id, status='pending_admin').all()
    recent_matches = Match.query.filter_by(league_id=league.id, status='approved').order_by(Match.id.desc()).limit(15).all()

    # ---> NEW: Fetch all custom awards for this league <---
    custom_awards = CustomAward.query.filter_by(league_id=league.id).all()

    # ---> NEW: Pass custom_awards to the template <---
    return render_template('admin.html',
                           league=league,
                           pending_players=pending_players,
                           players=approved_players,
                           seasons=seasons,
                           pending_matches=pending_matches,
                           recent_matches=recent_matches,
                           custom_awards=custom_awards)


@app.route('/<league_slug>/admin/change_password', methods=['POST'])
def change_admin_password(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    if session.get('admin_league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    new_password = request.form.get('new_password')
    if new_password:
        league.admin_password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash('Admin password updated successfully!', 'success')

    return redirect(url_for('admin', league_slug=league.url_slug))


@app.route('/<league_slug>/admin/approve_player/<int:player_id>')
def admin_approve_player(league_slug, player_id):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()
    if session.get('admin_league_id') != league.id: return redirect(url_for('login', league_slug=league.url_slug))

    player = Player.query.filter_by(id=player_id, league_id=league.id).first()
    if player:
        player.is_approved = True
        db.session.commit()
        flash(f"Player {player.name} approved!", "success")

    return redirect(url_for('admin', league_slug=league.url_slug))


@app.route('/<league_slug>/admin/reject_player/<int:player_id>')
def admin_reject_player(league_slug, player_id):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()
    if session.get('admin_league_id') != league.id: return redirect(url_for('login', league_slug=league.url_slug))

    player = Player.query.filter_by(id=player_id, league_id=league.id).first()
    if player:
        db.session.delete(player)
        db.session.commit()
        flash(f"Player rejected and deleted.", "success")

    return redirect(url_for('admin', league_slug=league.url_slug))


# --- ADMIN FORCE MATCH ROUTE ---
@app.route('/<league_slug>/admin/force_match', methods=['POST'])
def admin_force_match(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    # CORRECTED SECURITY CHECK: Look for admin_league_id, NOT 'admin'
    if session.get('admin_league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    match_type = request.form.get('match_type')
    p1_id = request.form.get('p1_id')
    p2_id = request.form.get('p2_id')
    outcome = request.form.get('outcome')

    if not p1_id or not p2_id or p1_id == p2_id:
        flash("Invalid players selected.", "error")
        return redirect(url_for('admin', league_slug=league.url_slug))

    match = Match(
        league_id=league.id,
        match_type=match_type,
        p1_id=p1_id,
        p2_id=p2_id,
        status='approved'
    )

    if match_type == '2v2':
        match.p1_partner_id = request.form.get('p1_partner_id')
        match.p2_partner_id = request.form.get('p2_partner_id')

    if outcome == 'team1_won':
        match.winner_id = p1_id
    else:
        match.winner_id = p2_id

    db.session.add(match)
    db.session.commit()

    if 'update_elos' in globals():

        update_elos(match)

    flash("Match successfully forced and approved!", "success")
    return redirect(url_for('admin', league_slug=league.url_slug))

@app.route('/<league_slug>/admin/grant_award', methods=['POST'])
def admin_grant_award(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()
    if session.get('admin_league_id') != league.id: return redirect(url_for('login', league_slug=league.url_slug))

    player_id = request.form.get('player_id')
    name = request.form.get('award_name')
    icon = request.form.get('award_icon')
    desc = request.form.get('award_desc')

    new_award = CustomAward(league_id=league.id, player_id=player_id, name=name, icon=icon, desc=desc)
    db.session.add(new_award)
    db.session.commit()

    flash(f"Custom award '{name}' granted!")
    return redirect(url_for('admin', league_slug=league.url_slug))


@app.route('/<league_slug>/admin/revoke_award/<int:award_id>')
def admin_revoke_award(league_slug, award_id):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    # Security check: Ensure they are actually logged in as the admin
    if session.get('admin_league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    # Find the specific award and make sure it belongs to this league
    award = CustomAward.query.filter_by(id=award_id, league_id=league.id).first()

    if award:
        db.session.delete(award)
        db.session.commit()
        flash(f"Custom award '{award.name}' successfully revoked.", "success")
    else:
        flash("Award not found or already deleted.", "error")

    return redirect(url_for('admin', league_slug=league.url_slug))


@app.route('/<league_slug>/admin/rename_season', methods=['POST'])
def admin_rename_season(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()
    if session.get('admin_league_id') != league.id: return redirect(url_for('login', league_slug=league.url_slug))

    season_id = request.form.get('season_id')
    new_name = request.form.get('new_name')

    if season_id and new_name:
        season = Season.query.filter_by(id=season_id, league_id=league.id).first()
        if season:
            season.name = new_name.strip()
            db.session.commit()
            flash("Season renamed.")

    return redirect(url_for('admin', league_slug=league.url_slug))


# --- MISSING ADMIN ACTION ROUTES ---

@app.route('/<league_slug>/admin/edit_elo', methods=['POST'])
def admin_edit_elo(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    # CORRECTED SECURITY CHECK: Look for admin_league_id, NOT 'admin'
    if session.get('admin_league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    player_id = request.form.get('player_id')
    new_elo = request.form.get('new_elo')

    if player_id and new_elo:
        player = Player.query.filter_by(id=player_id, league_id=league.id).first()
        if player:
            # Secure their old Elo before overriding it!
            current_peak = player.peak_elo if player.peak_elo is not None else 800
            player.peak_elo = max(player.elo, current_peak)

            # Apply the admin edit
            player.elo = int(new_elo)

            # Check if the admin gave them a new all-time high
            if player.elo > player.peak_elo:
                player.peak_elo = player.elo

            db.session.commit()
            flash(f"Elo for {player.name} updated to {new_elo}. Peak saved!", "success")

    return redirect(url_for('admin', league_slug=league.url_slug))


@app.route('/<league_slug>/admin/remove_player', methods=['POST'])
def admin_remove_player(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    # Security check: Ensure they are actually logged in as the admin
    if session.get('admin_league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    player_id = request.form.get('player_id')

    if player_id:
        player = Player.query.filter_by(id=player_id, league_id=league.id).first()
        if player:
            # 1. Delete all Custom Awards given to this player
            CustomAward.query.filter_by(player_id=player.id).delete()

            # 2. Delete all matches where this player participated in any slot
            Match.query.filter(
                or_(
                    Match.p1_id == player.id,
                    Match.p2_id == player.id,
                    Match.p1_partner_id == player.id,
                    Match.p2_partner_id == player.id
                )
            ).delete(synchronize_session=False)

            # 3. Now that the dependencies are gone, safely delete the player
            db.session.delete(player)
            db.session.commit()

            flash(f"Player {player.name} and their history have been successfully removed.", "success")

    return redirect(url_for('admin', league_slug=league.url_slug))


@app.route('/<league_slug>/admin/undo_match/<int:match_id>', methods=['POST'])
def admin_undo_match(league_slug, match_id):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    # Ensure admin is logged in
    if session.get('admin_league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    match = Match.query.filter_by(id=match_id, league_id=league.id, status='approved').first()
    if not match:
        flash("Match not found or already undone.", "error")
        return redirect(url_for('admin', league_slug=league.url_slug))

    # 1. Fetch the players
    p1 = Player.query.get(match.p1_id)
    p2 = Player.query.get(match.p2_id)

    # 2. Revert their Elos back to what they were before the match
    if match.p1_elo_pre is not None:
        p1.elo = match.p1_elo_pre
    if match.p2_elo_pre is not None:
        p2.elo = match.p2_elo_pre

    team1_won = (match.winner_id == match.p1_id) or (
                match.match_type == '2v2' and match.winner_id == match.p1_partner_id)

    # 3. Revert Wins/Losses for Team Captains
    if team1_won:
        if p1.wins > 0: p1.wins -= 1
        if p2.losses > 0: p2.losses -= 1
    else:
        if p2.wins > 0: p2.wins -= 1
        if p1.losses > 0: p1.losses -= 1

    # 4. Handle 2v2 partner reversions if applicable
    if match.match_type == '2v2':
        p1_partner = Player.query.get(match.p1_partner_id)
        p2_partner = Player.query.get(match.p2_partner_id)

        if p1_partner and match.p1_partner_elo_pre is not None:
            p1_partner.elo = match.p1_partner_elo_pre
        if p2_partner and match.p2_partner_elo_pre is not None:
            p2_partner.elo = match.p2_partner_elo_pre

        if team1_won:
            if p1_partner and p1_partner.wins > 0: p1_partner.wins -= 1
            if p2_partner and p2_partner.losses > 0: p2_partner.losses -= 1
        else:
            if p2_partner and p2_partner.wins > 0: p2_partner.wins -= 1
            if p1_partner and p1_partner.losses > 0: p1_partner.losses -= 1

    # 5. Delete the match from the database
    db.session.delete(match)
    db.session.commit()

    flash("Match successfully undone. Elo and Win/Loss stats have been reverted.", "success")
    return redirect(url_for('admin', league_slug=league.url_slug))

@app.route('/<league_slug>/admin/approve_match/<int:match_id>')
def admin_approve_match(league_slug, match_id):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()
    if session.get('admin_league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    match = Match.query.filter_by(id=match_id, league_id=league.id).first()
    if match and match.status == 'pending_admin':
        match.status = 'approved'
        db.session.commit()
        # Call the Elo update function we added earlier!
        if 'update_elos' in globals():
            # Save the Elos BEFORE they change so we can undo them later


            update_elos(match)
        flash("Match officially approved and Elos updated!", "success")

    return redirect(url_for('admin', league_slug=league.url_slug))


@app.route('/<league_slug>/admin/reject_match/<int:match_id>')
def admin_reject_match(league_slug, match_id):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()
    if session.get('admin_league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    match = Match.query.filter_by(id=match_id, league_id=league.id).first()
    if match and match.status == 'pending_admin':
        db.session.delete(match)
        db.session.commit()
        flash("Match rejected and deleted from the system.", "success")

    return redirect(url_for('admin', league_slug=league.url_slug))


@app.route('/<league_slug>/admin/end_season', methods=['POST'])
def admin_end_season(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()
    if session.get('admin_league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    new_season_name = request.form.get('new_season_name')
    active_season = Season.query.filter_by(league_id=league.id, is_active=True).first()

    if active_season:
        active_season.is_active = False

        # Save snapshot records for the Trophy/History view
        players = Player.query.filter_by(league_id=league.id).all()
        for p in players:
            record = SeasonRecord(
                league_id=league.id,
                player_id=p.id,
                player_name=p.name,
                season_id=active_season.id,
                final_elo=p.elo,
                wins=p.wins,
                losses=p.losses
            )
            db.session.add(record)

            # Reset player stats for the new season
            p.elo = 800
            p.wins = 0
            p.losses = 0

    # Create the new season
    if new_season_name:
        new_season = Season(name=new_season_name, is_active=True, league_id=league.id)
        db.session.add(new_season)

    db.session.commit()
    flash(f"Previous season archived! New season '{new_season_name}' has begun.", "success")
    return redirect(url_for('admin', league_slug=league.url_slug))


# --- PLAYER MANAGEMENT ADMIN ROUTES ---


@app.route('/<league_slug>/admin/change_password', methods=['POST'])
def admin_change_password(league_slug):
    league = League.query.filter_by(url_slug=league_slug).first_or_404()

    # Security check: Ensure they are actually logged in as the admin
    if session.get('admin_league_id') != league.id:
        return redirect(url_for('login', league_slug=league.url_slug))

    new_password = request.form.get('new_password')

    if new_password:
        # Update the admin password attached to the League table
        league.admin_password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash("Admin password successfully updated! Don't forget it.", "success")

    return redirect(url_for('admin', league_slug=league.url_slug))

@app.route('/sync_tables')
def sync_tables():
    db.create_all()
    return "All tables (including League and CustomAwards) have been successfully generated in Supabase!"

if __name__ == '__main__':
    app.run(debug=True)
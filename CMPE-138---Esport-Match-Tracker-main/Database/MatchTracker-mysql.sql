-- SJSU CMPE 138 FALL 2025 TEAM7 --
-- Match Maker Database -- 
-- DROP & CREATE TABLE --
DROP DATABASE IF EXISTS MatchTracker;
CREATE DATABASE MatchTracker;
USE MatchTracker;

-- TABLES --
CREATE TABLE UserAccount (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(50) UNIQUE NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    role           ENUM('admin', 'user') DEFAULT 'user'
);

-- For Demo: Admin Password = Admin123 ---
INSERT INTO UserAccount (username, password_hash, role)
VALUES (
	'admin', 
    '$2b$12$YfT5gtnm6tC9RMmgAWeHrucD/w//0g4lL95lWEtAFvXMFnSHjMlEu', 
    'admin'
);

CREATE TABLE Game(
    game_id VARCHAR(6) PRIMARY KEY, 
    game_name VARCHAR(50) NOT NULL,
    game_rules TEXT,
    game_team_size INT
);

CREATE TABLE Venue(
    venue_id       VARCHAR(9) PRIMARY KEY,
    venue_name     VARCHAR(30),
    venue_location VARCHAR(30),
    venue_capacity INT
);

CREATE TABLE PrizePool(
    prize_pool_id       VARCHAR(6) PRIMARY KEY,
    prize_pool_amount   INT,
    prize_pool_currency TEXT
);

CREATE TABLE Sponsor(
    sponsor_id      VARCHAR(6) PRIMARY KEY,
    sponsor_name    VARCHAR(50) NOT NULL,
    sponsor_type    VARCHAR(30),
    sponsor_contact VARCHAR(50)
);

CREATE TABLE Commentator(
    commentator_id         VARCHAR(6) PRIMARY KEY,
    commentator_name       VARCHAR(50) NOT NULL,
    commentator_experience VARCHAR(30),
    commentator_language   TEXT
);

CREATE TABLE Organizer(
    organizer_id           VARCHAR(6) PRIMARY KEY,
    organizer_name         VARCHAR(50) NOT NULL,
    organizer_organization VARCHAR(50),
    organizer_contact      VARCHAR(50)
);

CREATE TABLE Manager(
    manager_id      VARCHAR(6) PRIMARY KEY,
    manager_name    VARCHAR(50) NOT NULL,
    manager_contact VARCHAR(30)
);

CREATE TABLE Coach(
    coach_id        VARCHAR(6) PRIMARY KEY,
    coach_name      VARCHAR(50) NOT NULL,
    coach_specialty VARCHAR(50)
);

CREATE TABLE Team(
    team_id           VARCHAR(6)  PRIMARY KEY, 
    team_name         VARCHAR(50) NOT NULL,
    team_region       VARCHAR(30),
    team_achievements TEXT,
    team_earnings     DECIMAL(8, 2),

    manager_id VARCHAR(6),
    coach_id   VARCHAR(6),

    FOREIGN KEY (manager_id) REFERENCES Manager(manager_id),
    FOREIGN KEY (coach_id)   REFERENCES Coach(coach_id)
);

CREATE TABLE Tournament(
    tournament_id VARCHAR(6) PRIMARY KEY,
    tournament_name VARCHAR(50),
    tournament_rules TEXT,
    tournament_duration VARCHAR(30),
    tournament_schedule DATETIME,
    tournament_format VARCHAR(30),

    game_id       VARCHAR(6),
    venue_id      VARCHAR(9),
    prize_pool_id VARCHAR(6),
    organizer_id  VARCHAR(6),

    FOREIGN KEY (game_id)       REFERENCES Game(game_id),
    FOREIGN KEY (venue_id)      REFERENCES Venue(venue_id),
    FOREIGN KEY (prize_pool_id) REFERENCES PrizePool(prize_pool_id),
    FOREIGN KEY (organizer_id)  REFERENCES Organizer(organizer_id)
);

CREATE TABLE Placement(
    placement_id           VARCHAR(6) PRIMARY KEY,
    placement_rank         TEXT,
    placement_points       VARCHAR(3),
    placement_prize_amount DECIMAL(8,2),

    team_id VARCHAR(6),
    tournament_id VARCHAR(6),

    FOREIGN KEY (team_id) REFERENCES Team(team_id),
    FOREIGN KEY (tournament_id) REFERENCES Tournament(tournament_id)
);

CREATE TABLE Player(
    player_id        VARCHAR(6)   PRIMARY KEY,
    player_username  VARCHAR (30) NOT NULL,
    player_real_name VARCHAR (50),
    player_role      VARCHAR(30),
    player_rank      VARCHAR(20),
    player_aliases   TEXT,
    player_age       INT,
    player_games     TEXT
);

CREATE TABLE TeamPlayer(
    team_id   VARCHAR(6),
    player_id VARCHAR(6),

    PRIMARY KEY (team_id, player_id),

    FOREIGN KEY (team_id)   REFERENCES Team(team_id),
    FOREIGN KEY (player_id) REFERENCES Player(player_id)
);

CREATE TABLE PlayerGame(
    player_id VARCHAR(6),
    game_id   VARCHAR(6),

    PRIMARY KEY (player_id, game_id),

    FOREIGN KEY (player_id) REFERENCES Player(player_id),
    FOREIGN KEY (game_id)   REFERENCES Game(game_id)
);

CREATE TABLE MatchInfo(
    match_id        VARCHAR(6) PRIMARY KEY,
    match_rounds    INT,
    match_date_time DATETIME,
    match_results   TEXT,

    tournament_id    VARCHAR(6),
    game_id          VARCHAR(6),
    team1_id         VARCHAR(6),
    team2_id         VARCHAR(6),
    match_winner_id  VARCHAR(6),

    FOREIGN KEY (tournament_id)   REFERENCES Tournament(tournament_id),
    FOREIGN KEY (game_id)         REFERENCES Game(game_id),
    FOREIGN KEY (team1_id)        REFERENCES Team(team_id),
    FOREIGN KEY (team2_id)        REFERENCES Team(team_id),
    FOREIGN KEY (match_winner_id) REFERENCES Team(team_id)

);

CREATE TABLE MatchCommentator(
    match_id       VARCHAR(6),
    commentator_id VARCHAR(6),
    
    PRIMARY KEY (match_id, commentator_id),
    FOREIGN KEY (match_id)       REFERENCES MatchInfo(match_id),
    FOREIGN KEY (commentator_id) REFERENCES Commentator(commentator_id)
);

CREATE TABLE TournamentTeam(
    tournament_id VARCHAR(6),
    team_id       VARCHAR(6),
    placement_id  VARCHAR(6),

    PRIMARY KEY (tournament_id, team_id),

    FOREIGN KEY (tournament_id) REFERENCES Tournament(tournament_id),
    FOREIGN KEY (team_id)       REFERENCES Team(team_id),
    FOREIGN KEY (placement_id)  REFERENCES Placement(placement_id)
);

CREATE TABLE TournamentSponsor(
    tournament_id VARCHAR(6),
    sponsor_id    VARCHAR(6),

    PRIMARY KEY (tournament_id, sponsor_id),

    FOREIGN KEY (tournament_id) REFERENCES Tournament(tournament_id),
    FOREIGN KEY (sponsor_id)    REFERENCES Sponsor(sponsor_id)
);

CREATE TABLE TournamentCommentator(
    tournament_id  VARCHAR(6),
    commentator_id VARCHAR(6),

    PRIMARY KEY (tournament_id, commentator_id),

    FOREIGN KEY (tournament_id)  REFERENCES Tournament(tournament_id),
    FOREIGN KEY (commentator_id) REFERENCES Commentator(commentator_id)
);

CREATE VIEW UpcomingTournament AS
    SELECT T.tournament_id, 
           T.tournament_name,
           T.tournament_schedule, 
           T.tournament_format, 
           G.game_name 
    FROM Tournament T
    INNER JOIN Game G ON T.game_id = G.game_id
    ORDER BY tournament_schedule;

CREATE VIEW Format AS
    SELECT T.tournament_id, 
           T.tournament_name,
           T.tournament_schedule, 
           T.tournament_format, 
           G.game_name 
    FROM Tournament T
    INNER JOIN Game G ON T.game_id = G.game_id
    ORDER BY tournament_schedule;

CREATE VIEW PlacementPoints AS
    SELECT P.placement_id, 
           P.placement_rank, 
           P.placement_points, 
           P.placement_prize_amount,
           TM.team_name,   
           T.tournament_name
    FROM Placement P
    INNER JOIN Team TM On P.team_id = TM.team_id
    INNER JOIN Tournament T On P.tournament_id = T.tournament_id
    ORDER BY P.placement_points;

CREATE VIEW TournamentMatches AS
    SELECT M.match_id, 
           M.match_rounds, 
           M.match_date_time, 
           T1.team_name AS team1_name, 
           T2.team_name AS team2_name,
           WT.team_name AS winning_team_name,
           T.tournament_name
    FROM MatchInfo M
    INNER JOIN Tournament T ON M.tournament_id = T.tournament_id
    INNER JOIN Team T1 On M.team1_id = T1.team_id
    INNER JOIN Team T2 On M.team2_id = T2.team_id
    INNER JOIN TEAM WT On M.match_winner_id = WT.team_id
    ORDER BY M.match_date_time;

CREATE VIEW TournamentTeams AS
    SELECT TM.team_name, T.tournament_name
    FROM Team TM
    INNER JOIN TournamentTeam TT ON TM.team_id = TT.team_id
    INNER JOIN Tournament T ON TT.tournament_id = T.tournament_id
    ORDER BY TM.team_name;

CREATE VIEW TeamWins AS
    SELECT TM.team_name,
           T.tournament_name,
           COUNT(*) AS wins
    FROM Team TM
    INNER JOIN MatchInfo M ON TM.team_id = M.match_winner_id
    INNER JOIN Tournament T ON M.tournament_id = T.tournament_id
    GROUP BY TM.team_name, T.tournament_name;

-- CREATE VIEW TeamPlayers AS
--     SELECT T.team_name, P.player_real_name, P.player_real_name
--     FROM Player P
--     INNER JOIN TeamPlayer TP ON P.player_id = TP.player_id
--     INNER JOIN Team T ON T.team_id = TP.team_id
--     GROUP BY T.Team_name;

-- CREATE VIEW GameInfo AS
--     SELECT TM.team_name, T.tournament_name, O,organizer_name
--     FROM Team TM
--     INNER JOIN TournamentTeam TT ON TM.team_id = TT.team_id
--     INNER JOIN Tournament T ON TT.tournament_id = T.tournament_id
--     INNER JOIN Organizer O ON T.organizer_id = O.organizer_id
--     GROUP BY T.tournament_schedule
--     ORDER BY T.tournament_schedule DESC;


-- Populating The Tables --
-- Games -- 
INSERT INTO Game (game_id, game_name, game_rules, game_team_size) VALUES
('G001', 'League of Legends', 'MOBA with 3 lanes, destroy enemy nexus to win', 5),
('G002', 'Counter-Strike 2', 'Tactical FPS, plant/defuse bomb or eliminate enemies', 5),
('G003', 'Dota 2', 'MOBA with ancient defense objective', 5),
('G004', 'Valorant', 'Tactical shooter with agent abilities', 5),
('G005', 'Overwatch 2', 'Team-based hero shooter with objective modes', 5);

-- Tournaments --
INSERT INTO Tournament (tournament_id, tournament_name, tournament_rules, tournament_duration, tournament_schedule, tournament_format) VALUES
('T001', 'Worlds Championship 2024', 'Double elimination bracket, best of 5 finals', '30 days', '2024-10-15 09:00:00', 'Double Elimination'),
('T002', 'CS2 Major Berlin', 'Swiss system into single elimination playoffs', '14 days', '2024-11-20 10:00:00', 'Swiss + Single Elim'),
('T003', 'The International 2024', 'Group stage into double elimination bracket', '21 days', '2024-09-01 12:00:00', 'Double Elimination'),
('T004', 'Valorant Champions', 'Group stage into single elimination bracket', '18 days', '2024-08-10 11:00:00', 'Single Elimination'),
('T005', 'Overwatch League Finals', 'Best of 7 grand finals', '10 days', '2024-10-05 14:00:00', 'Playoffs');

-- Matches --
INSERT INTO MatchInfo (match_id, match_rounds, match_date_time) VALUES
('M001', 5, '2024-10-15 15:00:00'),
('M002', 3, '2024-10-16 18:00:00'),
('M003', 5, '2024-11-20 16:00:00'),
('M004', 3, '2024-09-01 13:00:00'),
('M005', 7, '2024-08-10 17:00:00');

-- Teams --
INSERT INTO Team (team_id, team_name, team_region, team_achievements, team_earnings) VALUES
('TM001', 'Cloud9', 'North America', 'Multiple LCS titles, Worlds semifinals', 500000.00),
('TM002', 'T1', 'South Korea', '4x World Champions, numerous LCK titles', 850000.00),
('TM003', 'FaZe Clan', 'Europe', 'CS Major winners, multiple tournament victories', 620000.00),
('TM004', 'Team Liquid', 'North America', 'TI winners, multiple regional championships', 780000.00),
('TM005', 'Fnatic', 'Europe', 'World Champions S1, multiple regional titles', 450000.00),
('TM006', 'Gen.G', 'South Korea', 'Worlds 2024 Champions, LCK titles', 680000.00);

-- Players -- 
INSERT INTO Player (player_id, player_username, player_real_name, player_role, player_rank, player_aliases, player_age, player_games) VALUES
('P001', 'Faker', 'Lee Sang-hyeok', 'Mid Laner', 'Challenger', 'The Unkillable Demon King', 28, 'League of Legends'),
('P002', 's1mple', 'Oleksandr Kostyliev', 'AWPer', 'Global Elite', 'The Ukrainian Star', 27, 'Counter-Strike 2'),
('P003', 'N0tail', 'Johan Sundstein', 'Support', 'Immortal', 'BigDaddy', 31, 'Dota 2'),
('P004', 'TenZ', 'Tyson Ngo', 'Duelist', 'Radiant', 'TenZ the Prodigy', 23, 'Valorant'),
('P005', 'Deft', 'Kim Hyuk-kyu', 'ADC', 'Challenger', 'Korean Marksman', 28, 'League of Legends'),
('P006', 'ZywOo', 'Mathieu Herbaut', 'AWPer', 'Global Elite', 'French Phenom', 24, 'Counter-Strike 2'),
('P007', 'Ceb', 'Sébastien Debs', 'Offlaner', 'Immortal', '7ckngMad', 32, 'Dota 2'),
('P008', 'Chronicle', 'Timofey Khromov', 'Initiator', 'Radiant', 'The Russian Wall', 21, 'Valorant');

-- Placements --
INSERT INTO Placement (placement_id, placement_rank, placement_points, placement_prize_amount, team_id, tournament_id) VALUES
('PL001', '1st', '100', 50000.00, 'TM003', 'T001'),
('PL002', '2nd', '75', 25000.00, 'TM002', 'T001'),
('PL003', '3rd', '50', 150000.00, 'TM005', 'T002'),
('PL004', '4th', '40', 100000.00, 'TM001', 'T003'),
('PL005', '5th', '30', 75000.00, 'TM004', 'T004'),
('PL006', '7th', '20', 50000.00, 'TM006', 'T005');

-- Venues --
INSERT INTO Venue (venue_id, venue_name, venue_location, venue_capacity) VALUES
('V001', 'Madison Square Garden', 'New York, USA', 20000),
('V002', 'Mercedes-Benz Arena', 'Berlin, Germany', 17000),
('V003', 'Climate Pledge Arena', 'Seattle, USA', 18000),
('V004', 'Gocheok Sky Dome', 'Seoul, South Korea', 16000),
('V005', 'Accor Arena', 'Paris, France', 20300);

-- Prize Pools --
INSERT INTO PrizePool (prize_pool_id, prize_pool_amount, prize_pool_currency) VALUES
('PP001', 2000000, 'USD'),
('PP002', 1500000, 'USD'),
('PP003', 40000000, 'USD'),
('PP004', 2250000, 'USD'),
('PP005', 3500000, 'USD');

-- Sponsors --
INSERT INTO Sponsor (sponsor_id, sponsor_name, sponsor_type, sponsor_contact) VALUES
('S001', 'Red Bull', 'Energy Drink', 'esports@redbull.com'),
('S002', 'Logitech G', 'Gaming Peripherals', 'partnerships@logitech.com'),
('S003', 'Intel', 'Technology', 'esports@intel.com'),
('S004', 'Mastercard', 'Financial Services', 'gaming@mastercard.com'),
('S005', 'HyperX', 'Gaming Hardware', 'esports@hyperx.com');

-- Commentators --
INSERT INTO Commentator (commentator_id, commentator_name, commentator_experience, commentator_language) VALUES
('C001', 'Trevor Henry', '10 years', 'English'),
('C002', 'Alex Richardson', '8 years', 'English, Spanish'),
('C003', 'Kim Min-ah', '6 years', 'Korean, English'),
('C004', 'Mitch Leslie', '12 years', 'English'),
('C005', 'OD Pixel', '9 years', 'English');

-- Organizers --
INSERT INTO Organizer (organizer_id, organizer_name, organizer_organization, organizer_contact) VALUES
('O001', 'John Martinez', 'Riot Games', 'j.martinez@riotgames.com'),
('O002', 'Sarah Chen', 'ESL Gaming', 's.chen@eslgaming.com'),
('O003', 'Erik Johnson', 'Valve Corporation', 'e.johnson@valvesoftware.com'),
('O004', 'Anna Petrov', 'Blast Premier', 'a.petrov@blast.tv'),
('O005', 'Marcus White', 'DreamHack', 'm.white@dreamhack.com');

-- Managers --
INSERT INTO Manager (manager_id, manager_name, manager_contact) VALUES
('MG001', 'Jack Etienne', 'jack@cloud9.gg'),
('MG002', 'Steve Arhancet', 'steve@teamliquid.com'),
('MG003', 'Sam Mathews', 'sam@fnatic.com'),
('MG004', 'Carlos Rodriguez', 'carlos@g2esports.com'),
('MG005', 'Andy Dinh', 'andy@tsm.gg');

-- Coaches --
INSERT INTO Coach (coach_id, coach_name, coach_specialty) VALUES
('CO001', 'Kim Jeong-gyun', 'Draft Strategy and Team Coordination'),
('CO002', 'Danny Sorensen', 'Tactical Analysis and Map Control'),
('CO003', 'Andreas Hoejsleth', 'Hero Selection and Game Theory'),
('CO004', 'Chet Singh', 'Agent Composition and Utility Usage'),
('CO005', 'Fabian Broich', 'Team Synergy and Communication');

-- =========================
-- 1) Link tournaments to game, venue, prize pool, organizer
-- =========================
UPDATE Tournament
SET game_id = 'G001', venue_id = 'V004', prize_pool_id = 'PP001', organizer_id = 'O001'
WHERE tournament_id = 'T001';  -- Worlds Championship 2024 -> LoL

UPDATE Tournament
SET game_id = 'G002', venue_id = 'V002', prize_pool_id = 'PP002', organizer_id = 'O002'
WHERE tournament_id = 'T002';  -- CS2 Major Berlin -> CS2

UPDATE Tournament
SET game_id = 'G003', venue_id = 'V003', prize_pool_id = 'PP003', organizer_id = 'O003'
WHERE tournament_id = 'T003';  -- The International 2024 -> Dota 2

UPDATE Tournament
SET game_id = 'G004', venue_id = 'V005', prize_pool_id = 'PP004', organizer_id = 'O004'
WHERE tournament_id = 'T004';  -- Valorant Champions -> Valorant

UPDATE Tournament
SET game_id = 'G005', venue_id = 'V001', prize_pool_id = 'PP005', organizer_id = 'O005'
WHERE tournament_id = 'T005';  -- OW League Finals -> Overwatch 2


-- =========================
-- 2) (Optional) link teams to managers/coaches (FKs on Team)
-- =========================
UPDATE Team SET manager_id = 'MG001', coach_id = 'CO004' WHERE team_id = 'TM001'; -- Cloud9
UPDATE Team SET manager_id = 'MG005', coach_id = 'CO001' WHERE team_id = 'TM002'; -- T1
UPDATE Team SET manager_id = 'MG004', coach_id = 'CO002' WHERE team_id = 'TM003'; -- FaZe
UPDATE Team SET manager_id = 'MG002', coach_id = 'CO003' WHERE team_id = 'TM004'; -- Team Liquid
UPDATE Team SET manager_id = 'MG003', coach_id = 'CO005' WHERE team_id = 'TM005'; -- Fnatic
UPDATE Team SET manager_id = 'MG001', coach_id = 'CO001' WHERE team_id = 'TM006'; -- Gen.G


-- =========================
-- 3) Player ↔ Game (junction) so you can fetch players by game
-- =========================
INSERT INTO PlayerGame (player_id, game_id) VALUES
('P001','G001'),  -- Faker -> LoL
('P005','G001'),  -- Deft -> LoL
('P002','G002'),  -- s1mple -> CS2
('P006','G002'),  -- ZywOo -> CS2
('P003','G003'),  -- N0tail -> Dota 2
('P007','G003'),  -- Ceb -> Dota 2
('P004','G004'),  -- TenZ -> Valorant
('P008','G004');  -- Chronicle -> Valorant


-- =========================
-- 4) Team ↔ Player (rosters) for sample data
-- =========================
INSERT INTO TeamPlayer (team_id, player_id) VALUES
('TM002','P001'),  -- T1: Faker
('TM002','P005'),  -- T1: Deft
('TM001','P004'),  -- Cloud9: TenZ
('TM003','P006'),  -- FaZe: ZywOo
('TM004','P003'),  -- Team Liquid: N0tail
('TM005','P008');  -- Fnatic: Chronicle


-- =========================
-- 5) Tournament ↔ Team (entrants) + sample placements
-- =========================
INSERT INTO TournamentTeam (tournament_id, team_id, placement_id) VALUES
('T001','TM002','PL001'), -- Worlds: T1 1st
('T001','TM006','PL002'), -- Worlds: Gen.G 2nd
('T001','TM001','PL005'), -- Worlds: Cloud9 5-6th
('T001','TM005','PL006'), -- Worlds: Fnatic 7-8th

('T002','TM003','PL001'), -- CS2 Major: FaZe 1st
('T002','TM005','PL002'), -- CS2 Major: Fnatic 2nd

('T003','TM004','PL001'), -- TI: Team Liquid 1st
('T003','TM005','PL003'), -- TI: Fnatic 3rd

('T004','TM001','PL002'), -- VCT Champs: Cloud9 2nd
('T004','TM005','PL004'); -- VCT Champs: Fnatic 4th


-- =========================
-- 6) Tournament ↔ Sponsor / Commentator (samples)
-- =========================
INSERT INTO TournamentSponsor (tournament_id, sponsor_id) VALUES
('T001','S001'), ('T001','S003'),
('T002','S002'), ('T002','S003'),
('T003','S003'), ('T003','S004'),
('T004','S004'), ('T004','S005'),
('T005','S001'), ('T005','S005');

INSERT INTO TournamentCommentator (tournament_id, commentator_id) VALUES
('T001','C001'), ('T001','C004'),
('T002','C002'),
('T003','C005'),
('T004','C004'),
('T005','C001');


-- =========================
-- 7) Update Matches to hook up game, tournament, teams
-- =========================
UPDATE MatchInfo
SET tournament_id = 'T001', game_id = 'G001', team1_id = 'TM002', team2_id = 'TM006',  match_winner_id = 'TM002'
WHERE match_id = 'M001';

UPDATE MatchInfo
SET tournament_id = 'T001', game_id = 'G001', team1_id = 'TM001', team2_id = 'TM005',  match_winner_id = 'TM005'
WHERE match_id = 'M002';

UPDATE MatchInfo
SET tournament_id = 'T002', game_id = 'G002', team1_id = 'TM003', team2_id = 'TM005',  match_winner_id = 'TM005'
WHERE match_id = 'M003';

UPDATE MatchInfo
SET tournament_id = 'T003', game_id = 'G003', team1_id = 'TM004', team2_id = 'TM005',  match_winner_id = 'TM004'
WHERE match_id = 'M004';

UPDATE MatchInfo
SET tournament_id = 'T004', game_id = 'G004', team1_id = 'TM001', team2_id = 'TM005',  match_winner_id = 'TM005'
WHERE match_id = 'M005';


-- =========================
-- 8) Match ↔ Commentator (samples)
-- =========================
INSERT INTO MatchCommentator (match_id, commentator_id) VALUES
('M001','C001'), ('M001','C004'),
('M002','C001'),
('M003','C002'),
('M004','C005'),
('M005','C004');
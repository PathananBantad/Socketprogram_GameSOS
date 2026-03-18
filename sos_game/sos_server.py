import socket
import threading
import json
import os

HOST = "localhost"
PORT = 8080
BOARD_SIZE = 3
LEADERBOARD_FILE = "leaderboard.json"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen()

print("Multithreaded Server running...")

clients = {}
waiting_queue = []
active_games = {}
leaderboard = {}

lock = threading.Lock()  # Protect shared resources

# ----------------------------
# Leaderboard Functions
# ----------------------------

def load_leaderboard():
    global leaderboard
    if os.path.exists(LEADERBOARD_FILE):
        with open(LEADERBOARD_FILE, "r") as f:
            leaderboard.update(json.load(f))

def save_leaderboard():
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(leaderboard, f, indent=4)

# ----------------------------
# Utility
# ----------------------------

def send(sock, data):
    sock.send((json.dumps(data) + "\n").encode())

def check_sos(board, r, c):
    directions = [(0,1), (1,0), (1,1), (1,-1)]
    count = 0
    rows = len(board)
    cols = len(board[0])

    for dr, dc in directions:
        # Case 1: Placed letter is middle O (S-O-S)
        if board[r][c] == "O":
            if 0 <= r-dr < rows and 0 <= c-dc < cols and \
               0 <= r+dr < rows and 0 <= c+dc < cols:
                if board[r-dr][c-dc] == "S" and board[r+dr][c+dc] == "S":
                    count += 1

        # Case 2: Placed letter is S (S-O-S starting here)
        if board[r][c] == "S":
            # Check forwards
            if 0 <= r+2*dr < rows and 0 <= c+2*dc < cols:
                if board[r+dr][c+dc] == "O" and board[r+2*dr][c+2*dc] == "S":
                    count += 1
            
            # Case 3: Placed letter is S (S-O-S ending here)
            # Check backwards
            if 0 <= r-2*dr < rows and 0 <= c-2*dc < cols:
                if board[r-dr][c-dc] == "O" and board[r-2*dr][c-2*dc] == "S":
                    count += 1

    return count

def board_full(board):
    return all(cell!=" " for row in board for cell in row)

# ----------------------------
# Game Class
# ----------------------------

class Game:
    def __init__(self, p1, p2):
        self.players = [p1, p2]
        self.board = [[" "]*BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.scores = {p1:0, p2:0}
        self.turn = 0

# ----------------------------
# Client Handler
# ----------------------------
def handle_client(conn):
    name = None
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break

            messages = data.decode().split("\n")
            for message in messages:
                if not message.strip():
                    continue

                payload = json.loads(message)
                ptype = payload.get("type")
                sender = payload.get("sender")

                # ---------------- REGISTER ----------------
                if ptype == "register":
                    with lock:
                        clients[conn] = sender
                        name = sender
                        if sender not in leaderboard:
                            leaderboard[sender] = {"win": 0, "lose": 0, "tie": 0}
                            save_leaderboard()
                    send(conn, {"msg": "Registered successfully"})

                # ---------------- PLAY ----------------
                elif ptype == "play":
                    with lock:
                        if sender not in waiting_queue:
                            waiting_queue.append(sender)
                        
                        if len(waiting_queue) >= 2:
                            p1 = waiting_queue.pop(0)
                            p2 = waiting_queue.pop(0)
                            game = Game(p1, p2)
                            active_games[p1] = game
                            active_games[p2] = game

                            for i, p in enumerate(game.players):
                                sock = next(s for s, n in clients.items() if n == p)
                                send(sock, {
                                    "msg": "Game Start",
                                    "game": {
                                        "board": game.board,
                                        "scores": game.scores,
                                        "turn": game.players[game.turn]
                                    }
                                })
                        else:
                            send(conn, {"msg": "Waiting for opponent..."})

                # ---------------- MOVE ----------------
                elif ptype == "move":
                    with lock:
                        game = active_games.get(sender)
                        if not game or game.players[game.turn] != sender:
                            continue

                        r, c, letter = payload["row"], payload["col"], payload["letter"]
                        if game.board[r][c] != " ":
                            continue

                        game.board[r][c] = letter
                        score = check_sos(game.board, r, c)
                        game.scores[sender] += score

                        if score == 0:
                            game.turn = 1 - game.turn

                        if board_full(game.board):
                            p1, p2 = game.players
                            s1, s2 = game.scores[p1], game.scores[p2]
                            if s1 > s2:
                                winner = p1
                                leaderboard[p1]["win"] += 1
                                leaderboard[p2]["lose"] += 1
                            elif s2 > s1:
                                winner = p2
                                leaderboard[p2]["win"] += 1
                                leaderboard[p1]["lose"] += 1
                            else:
                                winner = None
                                leaderboard[p1]["tie"] += 1
                                leaderboard[p2]["tie"] += 1
                            save_leaderboard()

                            for p in game.players:
                                sock = next((s for s, n in clients.items() if n == p), None)
                                if sock:
                                    send(sock, {"msg": "GAME_OVER", "board": game.board, "scores": game.scores, "winner": winner})
                                if p in active_games:
                                    del active_games[p]
                            continue

                        for p in game.players:
                            sock = next((s for s, n in clients.items() if n == p), None)
                            if sock:
                                send(sock, {"msg": "UPDATE", "board": game.board, "scores": game.scores, "turn": game.players[game.turn]})

                # ---------------- LEADERBOARD ----------------
                elif ptype == "leaderboard":
                    with lock:
                        sorted_board = dict(sorted(leaderboard.items(), key=lambda x: x[1]["win"], reverse=True))
                    send(conn, {"msg": "LEADERBOARD", "scores": sorted_board})

    except Exception as e:
        print(f"Error with {name}: {e}")
    finally:
        with lock:
            if name:
                print(f"Disconnected: {name}")
                if name in waiting_queue:
                    waiting_queue.remove(name)
                
                if name in active_games:
                    game = active_games[name]
                    opponent = next((p for p in game.players if p != name), None)
                    
                    if opponent:
                        leaderboard[opponent]["win"] += 1
                        leaderboard[name]["lose"] += 1
                        save_leaderboard()
                        
                        opp_sock = next((s for s, n in clients.items() if n == opponent), None)
                        if opp_sock:
                            send(opp_sock, {
                                "msg": "GAME_OVER", 
                                "winner": opponent,
                                "board": game.board,
                                "scores": game.scores,
                                "reason": f"Opponent {name} disconnected."
                            })
                        
                        if opponent in active_games:
                            del active_games[opponent]
                    
                    del active_games[name]
                
                clients.pop(conn, None)
        conn.close()

# ----------------------------
# Main
# ----------------------------

def main():
    load_leaderboard()

    while True:
        conn, addr = server.accept()
        print("Connected:", addr)
        threading.Thread(
            target=handle_client,
            args=(conn,),
            daemon=True
        ).start()

if __name__ == "__main__":
    main()
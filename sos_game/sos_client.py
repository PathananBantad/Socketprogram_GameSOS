import socket
import json
import sys

HOST = "localhost"
PORT = 8080

buffer = ""

def send(sock,data):
    sock.send((json.dumps(data)+"\n").encode())

def receive(sock):
    global buffer
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            print("Server disconnected.")
            sys.exit()

        buffer += chunk.decode()

        if "\n" in buffer:
            line, buffer = buffer.split("\n",1)
            return json.loads(line)

def print_board(board):
    print()
    for row in board:
        print(" | ".join(row))
        print("-"*10)
    print()

def main():
    sock = socket.socket()
    sock.connect((HOST,PORT))

    name = input("Enter your name: ")
    send(sock,{"type":"register","sender":name})
    print(receive(sock)["msg"])

    while True:
        print("\n1.Play\n2.Leaderboard\n3.Exit")
        choice = input("Choose: ")

        if choice=="1":
            send(sock,{"type":"play","sender":name})

            while True:
                data = receive(sock)
                msg = data["msg"]

                if msg=="Waiting for opponent...":
                    print(msg)

                elif msg=="Game Start":
                    print("\nGame Start")
                    print_board(data["game"]["board"])
                    print("Scores:",data["game"]["scores"])
                    print("Turn:",data["game"]["turn"])

                    if data["game"]["turn"]==name:
                        r,c,l=input("row col letter: ").split()
                        send(sock,{
                            "type":"move","sender":name,
                            "row":int(r),"col":int(c),
                            "letter":l.upper()
                        })

                elif msg=="UPDATE":
                    print_board(data["board"])
                    print("Scores:",data["scores"])
                    print("Turn:",data["turn"])

                    if data["turn"]==name:
                        r,c,l=input("row col letter: ").split()
                        send(sock,{
                            "type":"move","sender":name,
                            "row":int(r),"col":int(c),
                            "letter":l.upper()
                        })

                elif msg=="ERROR":
                    print("Error:",data["reason"])
                    r,c,l=input("row col letter: ").split()
                    send(sock,{
                        "type":"move","sender":name,
                        "row":int(r),"col":int(c),
                        "letter":l.upper()
                    })

                elif msg=="GAME_OVER":
                    print("\nGame Over")
                    print_board(data["board"])
                    print("Winner:",data["winner"])
                    break

        elif choice=="2":
            send(sock,{"type":"leaderboard","sender":name})
            data=receive(sock)
            print("\nLeaderboard:")
            for k,v in data["scores"].items():
                print(k,":",v)

        elif choice=="3":
            send(sock,{"type":"exit","sender":name})
            break

if __name__ == "__main__":
    main()
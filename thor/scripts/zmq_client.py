import zmq
import time

def main():
    """Simple ZeroMQ REP server for testing."""
    # Prepare our context and socket
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind("tcp://*:5555")
    print("ZeroMQ REP server started on tcp://*:5555")

    while True:
        #  Wait for next request from client
        message = socket.recv()
        print(f"Received request: {message.decode('utf-8')}")

        #  Do some 'work'
        time.sleep(1)  # Simulate some processing

        #  Send reply back to client
        reply_message = b"World"
        socket.send(reply_message)
        print(f"Sent reply: {reply_message.decode('utf-8')}")

if __name__ == "__main__":
    main()


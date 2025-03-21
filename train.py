#pgn for my own analysis on lichess
from datetime import date
import chess
import chess.engine
import chess.pgn
import random
import io
# Using stockfish on my system, you are free to choose Lc0 if you want gpu acceleration
# Path to Stockfish (installed via Homebrew)
STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"
engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

def count_non_losing_moves(board):
    """
    Counts the number of opponent moves that do NOT result in a significant disadvantage.
    A move is considered 'non-losing' if its evaluation is above -200 cp
    """
    legal_moves = list(board.legal_moves)
    move_evaluations = {}

    for move in legal_moves:
        board.push(move)
        info = engine.analyse(board, chess.engine.Limit(depth=10))
        eval_score = info["score"].relative.score() if info["score"].relative.score() is not None else 0
        move_evaluations[move] = eval_score
        board.pop()

    if not move_evaluations:
        return 0

    best_move = max(move_evaluations, key=move_evaluations.get, default=None)
    if best_move is None:
        return 0

    best_score = move_evaluations[best_move]
    if all(score < -200 for score in move_evaluations.values()):
        return 0

    return sum(1 for score in move_evaluations.values() if score > -200)

def compute_reward(board, move):
    """
    Reward function that encourages forcing the opponent into a tricky position
    where they have only one non-losing move.
    """
    board.push(move)
    non_losing_moves = count_non_losing_moves(board)
    info = engine.analyse(board, chess.engine.Limit(depth=10))
    score = info["score"].relative

    if score.is_mate():
        stockfish_eval = 10000 if score.mate() > 0 else -10000
    else:
        stockfish_eval = score.score()

    trick_bonus = 1.0 if stockfish_eval < 400 and non_losing_moves == 1 else 0.0

    #inverting since stockfish_eval is analysing from black's perspective
    base_reward = -stockfish_eval / 100.0

    board.pop()
    return base_reward+trick_bonus

def select_move(board, engine):
    """
    Selection function, parameters to change are depth and first 5 of the best suggestions
    Can add variability to match elo level of opponent
    This function is open to more research and is trainable on its own too.
    Maybe future implementation if I am unemployed.
    """
    info = engine.analyse(board, chess.engine.Limit(depth=5), multipv=5)
    legal_moves = list(board.legal_moves)
    moves = [entry['pv'][0] for entry in info if 'pv' in entry]
    if len(legal_moves)<1:
        return None
    # if len(moves) < 5:
    #     return random.choice(legal_moves)
    return moves[0] #if random.random() < 0.4 else moves[0]

def train_trick_stockfish(num_games=5):
    count = 0
    """
    Main function
    Monte Carlo simulations
    Runs self-play training, modifying Stockfish's move selection and printing PGN.
    """
    for game_num in range(num_games):
        count = 0
        board = chess.Board()
        game = chess.pgn.Game()  # Create a PGN game object
        game.headers["Event"] = f"Trick Stockfish Training Game {game_num + 1}"
        game.headers["Site"] = "Self-Play"
        game.headers["Date"] = str(date.today())
        game.headers["Round"] = str(game_num + 1)
        game.headers["White"] = "Trick Stockfish"
        game.headers["Black"] = "Stockfish"
        node = game

        while not board.is_game_over():
            legal_moves = list(board.legal_moves)
            if not legal_moves:
                print()
                break

            move_rewards = {move: compute_reward(board, move) for move in legal_moves}
            #print(move_rewards)
            best_trick_move = max((m for m in move_rewards if move_rewards[m] > 0.5),
                                  key=lambda m: move_rewards[m], default=None)
            #print(best_trick_move)
            if best_trick_move:
                board.push(best_trick_move)
            else:
                result = engine.play(board, chess.engine.Limit(depth=10))
                if result.move:
                    board.push(result.move)
                else:
                    break

            node = node.add_variation(board.peek())  # Add move to PGN

            selected_move = select_move(board, engine)
            if selected_move is None:
                break
            board.push(selected_move)
            node = node.add_variation(board.peek())  # Add move to PGN
            count+=1
            info = engine.analyse(board, chess.engine.Limit(depth=10))
            score = info["score"].relative
            if score.is_mate():
                stockfish_eval = 10000 if score.mate() > 0 else -10000
            else:
                stockfish_eval = score.score()
            if(count>=50):
                if(stockfish_eval<100 and stockfish_eval>-100):
                    print('Draw!')
                elif(stockfish_eval<-100):
                    print('Black wins!')
                else:
                    print('White wins!')
                break
        game.headers["Result"] = board.result()

        print(f"\nGame {game_num + 1} complete. Final Result: {board.result()}")
        print("Final Board Position:\n", board)

        # Print PGN
        pgn_io = io.StringIO()
        print(game, file=pgn_io)
        pgn_string = pgn_io.getvalue()
        print("\nPGN of the game:\n", pgn_string)

    engine.quit()

train_trick_stockfish()

#inverted the sign at count_non_losing moves
#added trick move display

#Potential futureworks:
#Move selections by opp
#Trick moves definition
#eval from any position
#WHITE SIDE WORK IN PROGRESS
#Dont compare with best move, rather use the current evaluation
#can I use stockfish tree without recalculating for each move?

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
#STOCKFISH_PATH = "./stockfish"
engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

FORKING_PIECES = {chess.KNIGHT, chess.PAWN, chess.BISHOP}

def enemies_attacked_by_piece_on(board, sq):
    piece = board.piece_at(sq)
    if piece is None:
        return set()
    enemy = not piece.color
    attacks = board.attacks(sq)
    return {
        s for s in chess.SQUARES
        if (p := board.piece_at(s)) and p.color == enemy and s in attacks
    }

def is_obvious_fork(board, move):
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type not in FORKING_PIECES:
        return False

    before = enemies_attacked_by_piece_on(board, move.from_square)
    board.push(move)
    after = enemies_attacked_by_piece_on(board, move.to_square)
    board.pop()

    new_targets = after - before
    if len(new_targets) != 2:
        return False

    return any(board.piece_at(sq).piece_type == chess.KING for sq in new_targets)

def obvious_moves(board, move):
    """
    Obvious replies that shouldn't count as a tricky defense:
    1. Any capture (including recaptures and en passant)
    2. Royal fork — new double attack on king + one other piece by knight/pawn/bishop
    """
    if board.is_capture(move):
        return True

    #if is_obvious_fork(board, move):
       # return True

    return False
def isTricky(board,prev_score): 
    """
    Counts the number of opponent moves(BLACK's) that do NOT result in a significant disadvantage.
    A move is considered 'non-losing' if its evaluation is within 200 cp of the best reply.
    """
    if len(board.piece_map()) < 15:
        return False, 0
    legal_moves = list(board.legal_moves)
    if len(legal_moves) < 5:
        return False, 0

    move_evaluations = {}
    for move in legal_moves:
        board.push(move)
        info = engine.analyse(board, chess.engine.Limit(depth=10))
        eval_score = info["score"].white().score() if info["score"].white().score() is not None else 0
        move_evaluations[move] = eval_score
        board.pop()

    if not move_evaluations:
        return False, 0

    best_move = min(move_evaluations, key=move_evaluations.get, default=None)
    if best_move is None:
        return False, 0

    best_score = move_evaluations[best_move]
    if all(score > 200 for score in move_evaluations.values()):
        return False, 0

    # Second-best tier: strictly worse than best, ties at best excluded
    worse_scores = [s for s in move_evaluations.values() if s > best_score]
    if not worse_scores:
        return False, 0
    second_highest = min(worse_scores)

    within_band = sum(1 for score in move_evaluations.values() if score <= best_score + 200)
    if within_band == 1 and second_highest > prev_score + 50:
        if obvious_moves(board, best_move):
            return False, 0
        return True, second_highest - prev_score
    return False, 0

def compute_reward(board, move):
    """
    Reward function that encourages forcing the opponent into a tricky position
    where they have only one non-losing move.
    """
    info = engine.analyse(board, chess.engine.Limit(depth=10))
    eval_score = info["score"].white().score() 
    if eval_score is None:
        eval_score = 0
    board.push(move)
    duo = isTricky(board,eval_score)
    info = engine.analyse(board, chess.engine.Limit(depth=10))
    score = info["score"].white()

    if score.is_mate():
        stockfish_eval = 10000 if score.mate() > 0 else -10000
    else:
        stockfish_eval = score.score()

    trick_bonus = 5*duo[1] if -150 < stockfish_eval < 200 and duo[0] else 0.0

    base_reward = stockfish_eval / 100.0

    board.pop()
    return base_reward,trick_bonus

def select_move(board, engine):
    """
    Selection function, parameters to change are depth and first 5 of the best suggestions
    Can add variability to match elo level of opponent
    This function is open to more research and is trainable on its own too.
    Maybe future implementation if I am unemployed.
    """
    info = engine.analyse(board, chess.engine.Limit(depth=10), multipv=5)
    legal_moves = list(board.legal_moves)
    moves = [entry['pv'][0] for entry in info if 'pv' in entry]
    if len(legal_moves)<1:
        return None
    # if len(moves) < 5:
    #     return random.choice(legal_moves)
    return moves[0] #if random.random() < 0.4 else moves[0]

def train_trick_stockfish(num_games=1):
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
            #define [m][0] and [m][1]
            # it is a normal gain and trick gain respectively

            best_trick_move = max((m for m in move_rewards if move_rewards[m][0] >-100),
                                  key=lambda m: move_rewards[m][0]+move_rewards[m][1], default=None)
            result = engine.play(board, chess.engine.Limit(depth=10))
            best_move = result.move
            #print(best_trick_move)
            if best_trick_move:
                board.push(best_trick_move)
                if(move_rewards[best_trick_move][1] > 0):
                    print(f"{best_trick_move} is a trick move! otherwise I was choosing {best_move} at move number {count+1}")  
                    #print(move_rewards)
            else:
                #result = engine.play(board, chess.engine.Limit(depth=10))
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
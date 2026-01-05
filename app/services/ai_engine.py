import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

class SeatFinderAI:
    def __init__(self):
        self.vectorizer = None
        self.nn_model = None
        self.search_tokens = []  
        self.token_map = {}      
        self.is_trained = False

    def train(self, student_data):
        """
        Expects list of dicts: 
        [{'registration_number': '...', 'roll_number': '...', 'seat': '...', ...}]
        """
        print(f"--- 🤖 AI TRAINING STARTED with {len(student_data)} records ---")
        
        if not student_data:
            print("❌ AI Error: No student data provided to train.")
            self.is_trained = False
            return

        self.search_tokens = []
        self.token_map = {}

        for s in student_data:
            # Index Registration Number
            if s.get('registration_number'):
                reg = str(s['registration_number']).strip()
                self.search_tokens.append(reg)
                self.token_map[reg] = s

            # Index Roll Number
            if s.get('roll_number'):
                roll = str(s['roll_number']).strip()
                self.search_tokens.append(roll)
                self.token_map[roll] = s

        # Validation
        if not self.search_tokens:
            print("❌ AI Error: No valid Registration/Roll numbers found.")
            self.is_trained = False
            return

        try:
            # 1. Convert strings to N-Grams (Vectorization)
            self.vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 3))
            tfidf_matrix = self.vectorizer.fit_transform(self.search_tokens)

            # 2. Fit KNN Model
            self.nn_model = NearestNeighbors(n_neighbors=1, metric='cosine')
            self.nn_model.fit(tfidf_matrix)
            self.is_trained = True
            print(f"✅ AI TRAINING COMPLETE. Indexed {len(self.search_tokens)} search keys.")
            
        except Exception as e:
            print(f"❌ AI Crash during training: {str(e)}")
            self.is_trained = False

    def find_seat(self, query):
        if not self.is_trained:
            return {"status": "error", "message": "AI not trained yet"}

        try:
            query_vec = self.vectorizer.transform([query])
            distances, indices = self.nn_model.kneighbors(query_vec)
            
            best_match_index = indices[0][0]
            confidence = 1 - distances[0][0]

            # Confidence Threshold (0.5 = 50% match)
            if confidence < 0.5:
                return {"status": "no_match", "confidence": round(confidence, 2)}

            matched_token = self.search_tokens[best_match_index]
            seat_info = self.token_map[matched_token]

            return {
                "status": "success",
                "match_found": matched_token,
                "confidence": round(confidence, 2),
                "seat_details": {
                    "building": seat_info.get('building', 'Unknown'),
                    "room": seat_info.get('room', 'Unknown'),
                    "seat": seat_info.get('seat', 'Unknown')
                }
            }
        except Exception as e:
            print(f"AI Search Error: {e}")
            return {"status": "error", "message": str(e)}

# Singleton instance
ai_engine = SeatFinderAI()
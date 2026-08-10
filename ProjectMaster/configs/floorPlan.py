class FloorPlan:
    BATHROOM_NAMES = {
        "bath",
        "bathroom",
        "full bathroom",
        "half bathroom",
        "ba",
        "bth",
        "main bathroom",
        "family bathroom",
        "common bathroom",
        "shared bathroom",
        "private bathroom",
        "master bathroom",
        "primary bathroom",
        "toilet",
        "wc",
        "water closet",
        "lavatory",
        "half bath",
        "guest toilet",
        "restroom",
        "bathroom/laundry",
        "bath/laundry",
        "bath/wc",
        "toilet/shower",
        "wc/shower",
        "shower",
        "shower room",
        "p.bath",
        "g.bath",
        "toil",
        "bathroom 1",
        "bathroom1",
        "bathroom2",
        "bathroom 2",
    }

    KITCHEN_NAMES = {
        "kitchen",
        "kitch",
        "kit",
        "kitchenette",
        "kitchen area",
        "kitchen zone",
        "cooking area",
        "cooking zone",
        "open kitchen",
        "open-plan kitchen",
        "open plan kitchen",
        "open kitchen area",
        "open-plan kitchen/living room",
        "open plan kitchen/living room",
        "kitchen/living room",
        "kitchen living room",
        "living room/kitchen",
        "living kitchen",
        "kitchen/dining room",
        "kitchen dining room",
        "dining room/kitchen",
        "kitchen/dining",
        "kitchen diner",
        "eat-in kitchen",
        "kitchen/family room",
        "kitchen/lounge",
        "lounge/kitchen",
        "studio kitchen",
        "compact kitchen",
        "small kitchen",
        "galley kitchen",
        "main kitchen",
        "shared kitchen",
        "communal kitchen",
        "service kitchen",
        "prep kitchen",
        "preparation kitchen",
        "secondary kitchen",
        "back kitchen",
        "butler's kitchen",
        "scullery",
        "pantry kitchen",
        "summer kitchen",
        "chef's kitchen",
        "commercial kitchen",
        "staff kitchen",
        "break room kitchen",
        "tea kitchen",
        "tea point",
        "refreshment area",
        "k",
        "kit.",
        "kitch.",
        "kt",
        "kitchenette/living room",
        "living room/kitchenette",
        "kitchenette/dining",
        "kitchenette area",
        "kitchen 1",
        "kitchen1",
        "kitchen 2",
        "kitchen2",
    }

    def __init__(self, rooms, doors, windows=None, openings=None):
        self.rooms = rooms or []
        self.doors = doors or []
        self.windows = windows or []
        self.openings = openings or []

        self.has_bathroom = False
        self.has_kitchen = False
        self.valid = self.is_valid()

    @staticmethod
    def normalize_room_name(name):
        """
        Converts room names into a consistent format.

        Example:
            "  BATHROOM  " -> "bathroom"
        """
        if not name:
            
            return ""
        #print(" ".join(str(name).strip().lower().split()))
        
        return " ".join(str(name).strip().lower().split())
    

    def is_bathroom(self, room_name):
        room_name = self.normalize_room_name(
            room_name
        )

        if room_name in self.BATHROOM_NAMES:
            return True

        bathroom_keywords = [
            "bathroom",
            "bath",
            "toilet",
            "wc",
            "water closet",
            "lavatory",
            "restroom",
            "shower",
        ]

        searchable_name = " " + " ".join(
            "".join(
                char if char.isalnum() else " "
                for char in room_name
            ).split()
        ) + " "

        for keyword in bathroom_keywords:

            searchable_keyword = " " + " ".join(
                "".join(
                    char if char.isalnum() else " "
                    for char in keyword
                ).split()
            ) + " "

            if searchable_keyword in searchable_name:
                return True

        return False


    def is_kitchen(self, room_name):
        room_name = self.normalize_room_name(
            room_name
        )

        if room_name in self.KITCHEN_NAMES:
            return True

        kitchen_keywords = [
            "kitchen",
            "kitchenette",
            "cooking area",
            "cooking zone",
            "cooking",
        ]

        searchable_name = " " + " ".join(
            "".join(
                char if char.isalnum() else " "
                for char in room_name
            ).split()
        ) + " "

        for keyword in kitchen_keywords:

            searchable_keyword = " " + " ".join(
                "".join(
                    char if char.isalnum() else " "
                    for char in keyword
                ).split()
            ) + " "

            if searchable_keyword in searchable_name:
                return True

        return False

    def is_valid(self):
        


        """
        A floor plan is valid when it contains:
        1. At least one bathroom
        2. At least one kitchen or cooking area

        Multiple rooms from the same category do not replace
        a missing room from the other category.
        """
        if not self.rooms:
            self.valid = False
            return False

        
        
        if not self.doors and not self.openings:
            self.valid= False
            return False
        
        

        self.has_bathroom = False
        self.has_kitchen = False

        for room in self.rooms:
            room_name = self.normalize_room_name(room.text)

            if self.is_bathroom(room_name):
                self.has_bathroom = True

            if self.is_kitchen(room_name):
                self.has_kitchen = True

            # Stop searching when both requirements are found.
            if self.has_bathroom and self.has_kitchen:
                break

        self.valid = self.has_bathroom and self.has_kitchen
        return self.valid


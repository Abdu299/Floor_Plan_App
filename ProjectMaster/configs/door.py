class door:
    def __init__(self,id, room1, room2, door_poly, confidence= None):
        self.id=id
        self.room1=room1
        self.room2=room2
        self.door_poly= door_poly
        self.confidence = confidence
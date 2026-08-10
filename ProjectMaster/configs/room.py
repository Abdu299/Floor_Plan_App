class Room:
    def __init__(self,id,image, roomPoly, doors=None, 
                 text=None,centroid= None, distFromCentroid= None, door= None, confidence= None):
        self.id=id
        self.doors= doors
        self.text= text
        self.centroid= centroid
        self.distFromCentroid= distFromCentroid
        self.image= image
        self.roomPoly= roomPoly
        self.door=door
        self.confidence= confidence
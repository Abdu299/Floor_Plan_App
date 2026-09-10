from ultralytics import YOLO
import PIL
import configs.helper as helper
import cv2
from detections.room_detection import imageToRooms
from shapely.geometry import Polygon
from configs.door import door
import numpy as np

class object_detect:
    model = YOLO("weights/best.pt")

    listRooms= []

    def __init__(self, label, img,draw_image, conf, listRooms, imageName= None, window= False):
        self.label = label
        self.img= img
        self.conf=conf
        self.listRooms =listRooms
        self.draw_image= draw_image
        self.imageName= imageName
        self.window= window



    def bbox_to_polygon(self, x1, y1, x2, y2):
        return Polygon([
            (x1, y1),
            (x2, y1),
            (x2, y2),
            (x1, y2)
        ])


    def find_connected_rooms(self, door_poly, max_room_distance, label):

        distances = []

        for room in self.listRooms:
            d = room.roomPoly.distance(door_poly)
            distances.append((d, room))

        distances.sort(key=lambda x: x[0])

        if label == "Door":
            # No detected rooms are available.
            if len(distances) == 0:
                return None, None, None

            # Keep the closest room exactly as before.
            distA, roomA = distances[0]

            # A door may now connect to one room only.
            # We do not call it an exterior door yet; that will be
            # decided later using the detected building boundary.
            if len(distances) == 1:
                return roomA, None, door_poly

            distB, roomB = distances[1]

            # Preserve the existing distance rule for the second room.
            # If the second room is too far away, keep the door with
            # only its closest room instead of discarding the door.
            if distB > max_room_distance:
                return roomA, None, door_poly

            return roomA, roomB, door_poly


#this methods takes the closest to the door with a distance
    def detect(self):

        img = self.img

        available_labels = ['Column','Curtain Wall','Dimension','Door','Railing','Sliding Door','Stair Case','Wall','Window']

        if self.label not in available_labels:
            return

        res = self.model.predict(img, conf=self.conf)

        filtered_boxes = [
            box for box in res[0].boxes
            if self.model.names[int(box.cls)] == self.label
        ]

        filtered_windows= None
        windows= []
        if self.window == True:
            filtered_windows = [
                box for box in res[0].boxes
                if self.model.names[int(box.cls)] == 'Window'
            ]
        
            
            for window in filtered_windows:
                x1, y1, x2, y2 = window.xyxy[0].tolist()
                windows.append(self.bbox_to_polygon(x1, y1, x2, y2))


        res[0].boxes = filtered_boxes

        box_list= []
        door_id=0
    #finding the coordinates
        for box in res[0].boxes:

            x1, y1, x2, y2 = box.xyxy[0].tolist()

            

            # create polygon
            door_poly = self.bbox_to_polygon(x1, y1, x2, y2)

            if self.label == "Door":
                #make the threshold
                door_width = abs(x2 - x1)
                max_room_distance = door_width // 5
                #print(f"The max distance for detecting a door in {self.imageName} is {max_room_distance}\n")

                # find connected rooms
                roomA, roomB, door_poly = self.find_connected_rooms(door_poly,max_room_distance, self.label)

                # A detected door must connect to at least one room.
                # roomB may be None for a possible exterior door.
                if roomA is None:
                    continue

                door_id+=1

                cv2.rectangle(
                    self.draw_image,
                    (int(x1), int(y1)),
                    (int(x2), int(y2)),
                    (0,0,255),
                    2
                )

                dooren = door(door_id, roomA, roomB, door_poly, confidence= float(box.conf[0]))
                

                box_list.append(dooren)

        if windows:
            for wind in windows:
                x1, y1, x2, y2 = wind.bounds

                cv2.rectangle(
                    self.draw_image,
                    (int(x1), int(y1)),
                    (int(x2), int(y2)),
                    (0, 0, 255),
                    2
                )
        
        #cv2.imwrite("Window_testing.png",img)
        return box_list, self.draw_image, windows
            





if __name__ == "__main__":
    name="images/floor-plani.jpg"
    listRooms, img=imageToRooms().returnRoom(name)

    obDet1 = object_detect("Window",img,0.1, listRooms)
    

    boxene, img= obDet1.detect()

    obDet = object_detect("Door",img,0.31, listRooms)

    boxene, img= obDet.detect()
    
    if boxene:
        for box in boxene:
            if box.room2 is None:
                print(
                    "Door connects room",
                    box.room1.text,
                    "and no second room (possible exterior door)"
                )
            else:
                print(
                    "Door connects room",
                    box.room1.text,
                    "and room",
                    box.room2.text
                )
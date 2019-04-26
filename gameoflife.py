import tkinter as tk
from tkinter import filedialog
from tkinter.messagebox import showerror
from PIL import Image

from time import sleep, time
import math
from collections import deque
from enum import Enum
import os

FPS = 30
CANVAS_SIZE = (1000, 800)
UPDATE_FREQS = [0.5, 0.25, 0.125, 0.06, 0.03]
MAX_CELLSIZE = 100
ZOOM_FREQ = 0.5
UNDO_HISTORY_LENGTH = 1000

class BrushType(Enum):
    default = 0 # has no mask
    plus = 1
    small_ship = 2
    glider_gun = 3

    # size of enum is manually updated
    SIZE = 4

BrushMasks = [None for i in range(BrushType.SIZE.value)]

def loadBrushMasks():
    rootdir = os.path.split(os.path.abspath(__file__))[0] + '/brushmasks/'
    for root, dirs, files in os.walk(rootdir):
        for filename in files:
            try:
                im = Image.open(f"{rootdir}/{filename}")
                pixels = im.load()
            except Exception as e:
                print("loadBrushMasks:", e)
                continue
            mask = []
            for i in range(im.size[0]):
                mask.append([])
                for j in range(im.size[1]):
                    if pixels[i,j][0] == 0: # black
                        mask[i].append(1)
                    else:
                        mask[i].append(0)
            try:
                BrushMasks[BrushType[filename.split('.')[0]].value] = mask
            except Exception as e:
                print("loadBrushMasks:", e)

def rotateMatrix(mat):
    if not len(mat): return
    top = 0
    bottom = len(mat)-1
    left = 0
    right = len(mat[0])-1
    while left < right and top < bottom:
        # Store the first element of next row, this element will replace first element of current row
        prev = mat[top+1][left]

        # Move elements of top row one step right
        for i in range(left, right+1):
            curr = mat[top][i]
            mat[top][i] = prev
            prev = curr
        top += 1

        # Move elements of rightmost column one step downwards
        for i in range(top, bottom+1):
            curr = mat[i][right]
            mat[i][right] = prev
            prev = curr
        right -= 1

        # Move elements of bottom row one step left
        for i in range(right, left-1, -1):
            curr = mat[bottom][i]
            mat[bottom][i] = prev
            prev = curr
        bottom -= 1

        # Move elements of leftmost column one step upwards
        for i in range(bottom, top-1, -1):
            curr = mat[i][left]
            mat[i][left] = prev
            prev = curr
        left += 1
    return mat

class GameState():
    def __init__(self):
        self.cells = []
        self.running = False

    def updateCells(self):
        self.cells = list(set(self.cells)) # remove dups
        next_gen_cells = []
        self.dead_cells = []
        self.new_cells = []
        self.cell_dict = dict(zip(self.cells, [0]*len(self.cells)))
        self.potential_cells = {}
        for cell in iter(self.cells):
            self.greetNeighbours(cell)
        for cell in self.cell_dict.keys():
            if self.generationStep(self.cell_dict[cell], alive=True):
                next_gen_cells.append(cell)
            else:
                self.dead_cells.append(cell)
        for cell in self.potential_cells.keys():
            if self.generationStep(self.potential_cells[cell], alive=False):
                next_gen_cells.append(cell)
                self.new_cells.append(cell)
        self.cells = next_gen_cells

    def greetNeighbours(self, cell):
        for i in range(cell[0]-1, cell[0]+2):
            for j in range(cell[1]-1, cell[1]+2):
                if cell != (i, j):
                    try:
                        self.cell_dict[(i, j)] += 1
                    except KeyError:
                        try:
                            self.potential_cells[(i, j)] += 1
                        except KeyError:
                            self.potential_cells[(i, j)] = 1

    def generationStep(self, count, alive):
        return (alive and count >= 2 and count <= 3) or ((not alive) and count == 3)

class SavedState():
    def __init__(self, cells):
        self.cells = cells


class Application(tk.Frame):
    def __init__(self, master=None):
        tk.Frame.__init__(self, master)
        self.grid(padx=5, pady=5)

        self.cellsize = 3
        self.brushtype = BrushType.default
        self.curBrushMask = None
        self.brushsize = 1
        self.brushrot = 0
        self.cell_rectangles = {}
        self.gamestate = GameState()
        self.lastSavedState = None
        self.undoStates = deque()

        self.viewOffset = (0, 0)

        self.update_freq_idx = 0
        self.lastUpdate = time()
        self.lastZoom = 0

        self.master.protocol("WM_DELETE_WINDOW", self.quit)
        self.createWidgets()
        self.drawGrid()

    ### Update ###
    def updateStep(self):
        if len(self.undoStates) >= UNDO_HISTORY_LENGTH:
            self.undoStates.popleft()
        self.undoStates.append(SavedState(self.gamestate.cells))

        self.gamestate.updateCells()
        self.removeDeadCells()
        self.addNewCells()

    def updateLoop(self):
        self.after(1000 // FPS, self.updateLoop)
        if self.gamestate.running:
            now = time()
            if now - self.lastUpdate >= UPDATE_FREQS[self.update_freq_idx]:
                self.lastUpdate = now
                self.updateStep()

    ### Input ###
    def leftClick(self, cell):
        if self.brushtype == BrushType.default:
            if self.brushsize == 1:
                self.interfaceAddCell(cell)
            else:
                halfbs = math.ceil(self.brushsize / 2)
                for i in range(-halfbs + (1 if self.brushsize % 2 else 0), halfbs):
                    for j in range(-halfbs + (1 if self.brushsize % 2 else 0), halfbs):
                        self.interfaceAddCell((cell[0] + i, cell[1] + j))
        else:
            halfwidth = int(len(self.curBrushMask) / 2)
            halfheight = int(len(self.curBrushMask[0]) / 2)
            for i in range(len(self.curBrushMask)):
                for j in range(len(self.curBrushMask[0])):
                    if self.curBrushMask[i][j]:
                        self.interfaceAddCell((cell[0] + i - halfwidth, cell[1] + j - halfheight))

    def leftClickedCanvasCallback(self, event):
        i = math.floor(event.x / self.cellsize) - self.viewOffset[0]
        j = math.floor(event.y / self.cellsize) - self.viewOffset[1]
        self.leftClick((i, j))

    def rightClick(self, cell):
        try:
            self.gamestate.cells.remove(cell)
        except ValueError:
            pass
        try:
            self.canvas.delete(self.cell_rectangles[cell])
            del self.cell_rectangles[cell]
        except KeyError:
            pass

    def rightClickedCanvasCallback(self, event):
        i = math.floor(event.x / self.cellsize) - self.viewOffset[0]
        j = math.floor(event.y / self.cellsize) - self.viewOffset[1]
        cell = (i, j)
        self.rightClick(cell)

    def zoomLocation(self, event):
        cx = int(self.canvas.winfo_width()  / 2)
        cy = int(self.canvas.winfo_height() / 2)
        self.viewOffset = (int((cx - event.x) / self.cellsize + self.viewOffset[0]), int((cy - event.y) / self.cellsize) + self.viewOffset[1])

    def zoomIn(self, event):
        now = time()
        if self.cellsize >= MAX_CELLSIZE or now - self.lastZoom < ZOOM_FREQ: return
        self.lastZoom = now
        self.cellsize += 1
        self.zoomLocation(event)
        self.refreshView()

    def zoomOut(self, event):
        now = time()
        if self.cellsize <= 2 or now - self.lastZoom < ZOOM_FREQ: return
        self.lastZoom = now
        self.cellsize -= 1
        self.zoomLocation(event)
        self.refreshView()

    def handleKey(self, event):
        if   event.keycode in [111, 25]: # Up
            self.viewOffset = (self.viewOffset[0], self.viewOffset[1] + 1)
        elif event.keycode in [113, 38]: # Left
            self.viewOffset = (self.viewOffset[0] + 1, self.viewOffset[1])
        elif event.keycode in [114, 40]: # Right
            self.viewOffset = (self.viewOffset[0] - 1, self.viewOffset[1])
        elif event.keycode in [116, 39]: # Down
            self.viewOffset = (self.viewOffset[0], self.viewOffset[1] - 1)
        else:
            #print(event.keycode)
            return
        self.refreshView(drawGrid=False)

    def toggleGameUpdates(self):
            self.gamestate.running = not self.gamestate.running

    def saveState(self):
        self.lastSavedState = SavedState(self.gamestate.cells)

    def saveStateToFile(self):
        filename = filedialog.asksaveasfilename(initialdir=__file__, title="Select state file", filetypes=(("text", "*.txt"), ("all files", "*.*")))
        if filename:
            with open(filename, 'w') as fd:
                for cell in self.gamestate.cells:
                    fd.write(f"{cell[0]},{cell[1]}\n")

    def loadStateFromFile(self):
        filename = filedialog.askopenfilename(initialdir=__file__, title="Select state file", filetypes=(("text", "*.txt"), ("all files", "*.*")))
        if filename:
            linecount = 0
            newcells = []
            lowestCoords = None
            with open(filename, 'r') as fd:
                try:
                    for line in fd:
                        linecount += 1
                        cell_parts = line.split(',')
                        if len(cell_parts) != 2:
                            raise ValueError
                        cell = (int(cell_parts[0]), int(cell_parts[1]))
                        if lowestCoords:
                            lowestCoords = (min(lowestCoords[0], cell[0]), min(lowestCoords[1], cell[1]))
                        else:
                            lowestCoords = cell
                        newcells.append(cell)
                except ValueError:
                    showerror(title="Load error", message="Error loading state save file on line %d" % linecount)
                    return
            self.viewOffset = (-lowestCoords[0], -lowestCoords[1])
            self.gamestate.cells = newcells
            self.refreshView()

    def loadState(self):
        if self.lastSavedState:
            self.gamestate.cells = self.lastSavedState.cells
            self.refreshView()

    def clearState(self):
        self.gamestate.cells = []
        self.refreshView()

    def manualStep(self):
        self.updateStep()

    def manualStepBack(self):
        if len(self.undoStates) > 0:
            self.gamestate.cells = self.undoStates.pop().cells
            self.refreshView()

    def updateSpeedLabel(self):
        self.speedStringVar.set(f"Speed: x{self.update_freq_idx + 1}")

    def increaseSpeed(self):
        if self.update_freq_idx >= len(UPDATE_FREQS)-1: return
        self.update_freq_idx += 1
        self.updateSpeedLabel()

    def decreaseSpeed(self):
        if self.update_freq_idx <= 0: return
        self.update_freq_idx -= 1
        self.updateSpeedLabel()

    def updateBrushSizeLabel(self):
        self.brushSizeVar.set(f"Brush size: {self.brushsize}")

    def increaseBrushSize(self):
        if self.brushsize >= 9: return
        self.brushsize += 1
        self.updateBrushSizeLabel()

    def decreaseBrushSize(self):
        if self.brushsize <= 1: return
        self.brushsize -= 1
        self.updateBrushSizeLabel()

    def updateBrushRotLabel(self):
        self.brushRotVar.set(f"Brush rotation: {self.brushrot}")

    def rotateBrushLeft(self):
        if self.brushtype not in [BrushType.small_ship]: return
        self.brushrot -= 90
        if self.brushrot < 0:
            self.brushrot = 270
        self.curBrushMask = rotateMatrix(rotateMatrix(self.curBrushMask))
        self.updateBrushRotLabel()

    def rotateBrushRight(self):
        pass
        #self.brushrot += 90
        #if self.brushrot >= 360:
        #    self.brushrot = 0
        #self.updateBrushRotLabel()

    def selectBrush(self, brush):
        self.brushtype = brush
        self.brushrot = 0
        self.updateBrushRotLabel()
        self.curBrushMask = BrushMasks[self.brushtype.value]

    ### Init ###
    def createWidgets(self):
        quitButton = tk.Button(self, text='Quit', command=self.quit, width=10)
        quitButton.grid(row=0, column=0, sticky="NW")

        gameControlFrame = tk.Frame(self)
        gameControlFrame.grid(row=0, column=1, sticky="NE")
        startButton = tk.Button(gameControlFrame, text='Start/Pause', command=self.toggleGameUpdates, width=10)
        startButton.grid(row=0, column=0)
        stepButton = tk.Button(gameControlFrame, text='Step', command=self.manualStep, width=10)
        stepButton.grid(row=0, column=1)
        stepBackButton = tk.Button(gameControlFrame, text='Step back', command=self.manualStepBack, width=10)
        stepBackButton.grid(row=0, column=2)
        self.speedStringVar = tk.StringVar()
        self.updateSpeedLabel()
        speedLabel = tk.Label(gameControlFrame, textvariable=self.speedStringVar)
        speedLabel.grid(row=1, column=0)
        speedDecreaseButton = tk.Button(gameControlFrame, text='Slower', command=self.decreaseSpeed, width=10)
        speedDecreaseButton.grid(row=1, column=1)
        speedIncreaseButton = tk.Button(gameControlFrame, text='Faster', command=self.increaseSpeed, width=10)
        speedIncreaseButton.grid(row=1, column=2)

        stateControlFrame = tk.Frame(self)
        stateControlFrame.grid(row=0, column=2, sticky="E")
        saveButton = tk.Button(stateControlFrame, text='Quicksave', command=self.saveState, width=10)
        saveButton.grid(row=0, column=0)
        loadButton = tk.Button(stateControlFrame, text='Load quicksave', command=self.loadState, width=10)
        loadButton.grid(row=0, column=1)
        clearButton = tk.Button(stateControlFrame, text='Clear state', command=self.clearState, width=10)
        clearButton.grid(row=0, column=2)
        saveToFileButton = tk.Button(stateControlFrame, text='Save to file', command=self.saveStateToFile, width=10)
        saveToFileButton.grid(row=1, column=0)
        loadFromFileButton = tk.Button(stateControlFrame, text='Load from file', command=self.loadStateFromFile, width=10)
        loadFromFileButton.grid(row=1, column=1)

        self.canvas = tk.Canvas(self, width=CANVAS_SIZE[0], height=CANVAS_SIZE[1], bg='black', bd=2, relief="groove")
        self.canvas.bind("<Button-1>", self.leftClickedCanvasCallback)
        self.canvas.bind("<Button-3>", self.rightClickedCanvasCallback)
        self.canvas.bind("<B1-Motion>", self.leftClickedCanvasCallback)
        self.canvas.bind("<B3-Motion>", self.rightClickedCanvasCallback)
        self.canvas.bind("<Button-4>", self.zoomIn)
        self.canvas.bind("<Button-5>", self.zoomOut)
        self.canvas.bind("<Key>", self.handleKey)
        self.canvas.focus_set()
        self.canvas.grid(row=1, column=0, columnspan=3)

        brushFrame = tk.Frame(self, width=50)
        brushFrame.grid(row=1, column=3, sticky="NW")

        brushSizeFrame = tk.Frame(brushFrame)
        brushSizeFrame.grid(row=0, column=0, sticky="NW", pady=(0, 20))
        self.brushSizeVar = tk.StringVar()
        self.updateBrushSizeLabel()
        brushSizeLabel = tk.Label(brushSizeFrame, textvariable=self.brushSizeVar, anchor="w", width=20)
        brushSizeLabel.grid(row=0, column=0, columnspan=2, sticky='W')
        decreaseBrushSizeButton = tk.Button(brushSizeFrame, text='-', command=self.decreaseBrushSize, width=4)
        decreaseBrushSizeButton.grid(row=1, column=0, sticky="W")
        increaseBrushSizeButton = tk.Button(brushSizeFrame, text='+', command=self.increaseBrushSize, width=4)
        increaseBrushSizeButton.grid(row=1, column=1, sticky="W")

        brushRotFrame = tk.Frame(brushFrame)
        brushRotFrame.grid(row=1, column=0, sticky="NW", pady=(0, 20))
        self.brushRotVar = tk.StringVar()
        self.updateBrushRotLabel()
        brushRotLabel = tk.Label(brushRotFrame, textvariable=self.brushRotVar, anchor="w", width=20)
        brushRotLabel.grid(row=0, column=0, columnspan=2, sticky='W')
        rotateBrushLeftButton = tk.Button(brushRotFrame, text='<-', command=self.rotateBrushLeft, width=4)
        rotateBrushLeftButton.grid(row=1, column=0, sticky='W')
        rotateBrushRightButton = tk.Button(brushRotFrame, text='->', command=self.rotateBrushRight, width=4)
        rotateBrushRightButton.grid(row=1, column=1, sticky="W")

        brushTypeFrame = tk.Frame(brushFrame)
        brushTypeFrame.grid(row=2, column=0, sticky="NW")
        brushLabel = tk.Label(brushTypeFrame, text="Brushes:", anchor="w", width=20)
        brushLabel.grid(row=0, column=0, sticky="W")
        defaultBrushButton = tk.Button(brushTypeFrame, text='Default brush', command=lambda: self.selectBrush(BrushType.default), width=12)
        defaultBrushButton.grid(row=1, column=0, columnspan=2, sticky="W")
        plusBrushButton = tk.Button(brushTypeFrame, text='Plus', command=lambda: self.selectBrush(BrushType.plus), width=12)
        plusBrushButton.grid(row=2, column=0, columnspan=2, sticky="W")
        smallshipBrushButton = tk.Button(brushTypeFrame, text='Small spaceship', command=lambda: self.selectBrush(BrushType.small_ship), width=12)
        smallshipBrushButton.grid(row=3, column=0, columnspan=2, sticky="W")
        glidergunBrushButton = tk.Button(brushTypeFrame, text='Glider gun', command=lambda: self.selectBrush(BrushType.glider_gun), width=12)
        glidergunBrushButton.grid(row=4, column=0, columnspan=2, sticky="W")

    ### Drawing ###
    def refreshView(self, drawGrid=True):
        if drawGrid:
            self.canvas.delete(tk.ALL)
            self.drawGrid()
        else:
            for cell in list(self.cell_rectangles.keys()):
                self.canvas.delete(self.cell_rectangles[cell])
                del self.cell_rectangles[cell]
        self.drawCells()

    def addCell(self, cell):
        x = (cell[0] + self.viewOffset[0])*self.cellsize
        y = (cell[1] + self.viewOffset[1])*self.cellsize
        self.cell_rectangles[cell] = self.canvas.create_rectangle(x, y, x + self.cellsize, y + self.cellsize, fill="OrangeRed2", outline="gray22")

    def interfaceAddCell(self, cell):
        if cell not in self.gamestate.cells:
            self.gamestate.cells.append(cell)
            self.addCell(cell)

    def addNewCells(self):
        for cell in self.gamestate.new_cells:
            self.addCell(cell)

    def removeDeadCells(self):
        for cell in self.gamestate.dead_cells:
            if cell in self.cell_rectangles:
                self.canvas.delete(self.cell_rectangles[cell])
                del self.cell_rectangles[cell]

    def drawCells(self):
        for cell in self.gamestate.cells:
            cellx = (cell[0] + self.viewOffset[0]) * self.cellsize
            celly = (cell[1] + self.viewOffset[1]) * self.cellsize
            if  cellx >= 0 and cellx <= self.canvas.winfo_width() \
            and celly >= 0 and celly <= self.canvas.winfo_height():
                self.addCell(cell)

    def drawGrid(self):
        i = 0
        self.update()
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        while i < w:
            self.canvas.create_line(i, 0, i, h, fill="gray22")
            i += self.cellsize
        i = 0
        while i < h:
            self.canvas.create_line(0, i, w, i, fill="gray22")
            i += self.cellsize

if __name__ == "__main__":
    loadBrushMasks()
    root = tk.Tk()
    app = Application(root)
    app.master.title("Game of Life")
    app.after(1000 // FPS, app.updateLoop)
    app.mainloop()
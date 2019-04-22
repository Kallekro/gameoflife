import tkinter as tk
from time import sleep, time
import threading
import math
import queue
from collections import deque

CANVAS_SIZE = (1000, 800)
MAX_CELLSIZE = 100
UPDATE_FREQ = 0.5
ZOOM_FREQ = 0.5

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

def queueInput(func):
    def queue_wrapper(*args):
        args[0].inputQueue.put((func, args))
    return queue_wrapper

class Application(tk.Frame):
    def __init__(self, master=None):
        tk.Frame.__init__(self, master)
        self.grid(padx=5, pady=5)
        self.createWidgets()

        self.shutdown = False
        self.inputQueue = queue.Queue()

        self.cellsize = 20
        self.cell_rectangles = {}
        self.gamestate = GameState()
        self.lastSavedState = None
        self.undoStates = deque()

        self.viewOffset = (0, 0)
        self.updatelock = threading.Lock()
        self.updateWorker = threading.Thread(target=self.updateLoop)
        self.lastUpdate = time()
        self.lastZoom = 0
        self.drawGrid()
        self.master.protocol("WM_DELETE_WINDOW", self.quitApp)
        self.updateWorker.start()

    def quitApp(self):
        with self.updatelock:
            self.shutdown = True
        self.inputQueue.join()
        self.updateWorker.join()
        self.quit()

    ### Update ###
    def updateStep(self):
        if len(self.undoStates) >= 100:
            self.undoStates.popleft()
        self.undoStates.append(SavedState(self.gamestate.cells))

        self.gamestate.updateCells()
        self.removeDeadCells()
        self.addNewCells()

    def popQueuedInput(self, block):
        f, args = self.inputQueue.get(block)
        if len(args) == 2:
            f(self, args[1]) # event input
        else:
            f(self) # button press
        self.inputQueue.task_done()

    def updateLoop(self):
        while 1:
            with self.updatelock:
                if self.shutdown:
                    while not self.inputQueue.empty():
                        self.popQueuedInput(True)
                    return
                if self.gamestate.running:
                    now = time()
                    if now - self.lastUpdate > UPDATE_FREQ:
                        self.lastUpdate = now
                        self.updateStep()
            try:
                self.popQueuedInput(False)
            except queue.Empty:
                pass

    ### Input ###
    @queueInput
    def leftClickedCanvasCallback(self, event):
        i = math.floor(event.x / self.cellsize) - self.viewOffset[0]
        j = math.floor(event.y / self.cellsize) - self.viewOffset[1]
        self.interfaceAddCell((i, j))

    @queueInput
    def rightClickedCanvasCallback(self, event):
        i = math.floor(event.x / self.cellsize) - self.viewOffset[0]
        j = math.floor(event.y / self.cellsize) - self.viewOffset[1]
        cell = (i, j)
        try:
            self.gamestate.cells.remove(cell)
        except ValueError:
            pass
        try:
            self.canvas.delete(self.cell_rectangles[cell])
            del self.cell_rectangles[cell]
        except KeyError:
            pass

    def zoomLocation(self, event):
        cx = int(self.canvas.winfo_width()  / 2)
        cy = int(self.canvas.winfo_height() / 2)
        self.viewOffset = (int((cx - event.x) / self.cellsize + self.viewOffset[0]), int((cy - event.y) / self.cellsize) + self.viewOffset[1])

    @queueInput
    def zoomIn(self, event):
        now = time()
        if self.cellsize >= MAX_CELLSIZE or now - self.lastZoom < ZOOM_FREQ: return
        self.lastZoom = now
        self.cellsize += 1
        self.zoomLocation(event)
        self.refreshView()

    @queueInput
    def zoomOut(self, event):
        now = time()
        if self.cellsize <= 2 or now - self.lastZoom < ZOOM_FREQ: return
        self.lastZoom = now
        self.cellsize -= 1
        self.zoomLocation(event)
        self.refreshView()

    @queueInput
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

    ### State control ###
    @queueInput
    def toggleGameUpdates(self):
            self.gamestate.running = not self.gamestate.running

    @queueInput
    def saveState(self):
        self.lastSavedState = SavedState(self.gamestate.cells)

    @queueInput
    def loadState(self):
        if self.lastSavedState:
            self.gamestate.cells = self.lastSavedState.cells
            self.refreshView()

    @queueInput
    def clearState(self):
        self.gamestate.cells = []
        self.refreshView()

    @queueInput
    def manualStep(self):
        self.updateStep()

    @queueInput
    def manualStepBack(self):
        if len(self.undoStates) > 0:
            self.gamestate.cells = self.undoStates.pop().cells
            self.refreshView()

    ### Init ###
    def createWidgets(self):
        self.quitButton = tk.Button(self, text='Quit', command=self.quitApp)
        self.quitButton.grid(row=0, column=0, sticky="W")

        self.gameControlFrame = tk.Frame(self)
        self.gameControlFrame.grid(row=0, column=1, sticky="E")
        self.startButton = tk.Button(self.gameControlFrame, text='Start/Pause', command=self.toggleGameUpdates)
        self.startButton.grid(row=0, column=0)
        self.stepButton = tk.Button(self.gameControlFrame, text='Step', command=self.manualStep)
        self.stepButton.grid(row=0, column=1)
        self.stepButton = tk.Button(self.gameControlFrame, text='Step back', command=self.manualStepBack)
        self.stepButton.grid(row=0, column=2)

        self.stateControlFrame = tk.Frame(self)
        self.stateControlFrame.grid(row=0, column=2, sticky="E")
        self.saveButton = tk.Button(self.stateControlFrame, text='Save state', command=self.saveState)
        self.saveButton.grid(row=0, column=0)
        self.loadButton = tk.Button(self.stateControlFrame, text='Reload state', command=self.loadState)
        self.loadButton.grid(row=0, column=1)
        self.loadButton = tk.Button(self.stateControlFrame, text='Clear state', command=self.clearState)
        self.loadButton.grid(row=0, column=2)

        self.canvas = tk.Canvas(self, width=CANVAS_SIZE[0], height=CANVAS_SIZE[1], bg='white', bd=2, relief="groove")
        self.canvas.bind("<Button-1>", self.leftClickedCanvasCallback)
        self.canvas.bind("<Button-3>", self.rightClickedCanvasCallback)
        self.canvas.bind("<B1-Motion>", self.leftClickedCanvasCallback)
        self.canvas.bind("<B3-Motion>", self.rightClickedCanvasCallback)
        self.canvas.bind("<Button-4>", self.zoomIn)
        self.canvas.bind("<Button-5>", self.zoomOut)
        self.canvas.bind("<Key>", self.handleKey)
        self.canvas.focus_set()
        self.canvas.grid(row=1, column=0, columnspan=3)

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
        self.cell_rectangles[cell] = self.canvas.create_rectangle(x, y, x + self.cellsize, y + self.cellsize, fill="blue")

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
            self.canvas.create_line(i, 0, i, h)
            i += self.cellsize
        i = 0
        while i < h:
            self.canvas.create_line(0, i, w, i)
            i += self.cellsize

if __name__ == "__main__":
    root = tk.Tk()
    app = Application(root)
    app.master.title("Game of Life")
    app.mainloop()
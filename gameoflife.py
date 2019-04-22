import tkinter as tk
from tkinter import filedialog
from tkinter.messagebox import showerror
from time import sleep, time
import threading
import math
import queue
from collections import deque

CANVAS_SIZE = (1000, 800)
UPDATE_FREQS = [0.5, 0.25, 0.125, 0.06, 0.03]
MAX_CELLSIZE = 100
ZOOM_FREQ = 0.5
UNDO_HISTORY_LENGTH = 1000

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

        self.shutdown = False
        self.inputQueue = queue.Queue()

        self.cellsize = 20
        self.cell_rectangles = {}
        self.gamestate = GameState()
        self.lastSavedState = None
        self.undoStates = deque()

        self.viewOffset = (0, 0)

        self.update_freq_idx = 0
        self.updatelock = threading.Lock()
        self.updateWorker = threading.Thread(target=self.updateLoop)
        self.lastUpdate = time()
        self.lastZoom = 0

        self.master.protocol("WM_DELETE_WINDOW", self.quitApp)
        self.createWidgets()
        self.drawGrid()
        self.updateWorker.start()

    def quitApp(self):
        with self.updatelock:
            self.shutdown = True
        self.inputQueue.join()
        self.updateWorker.join()
        self.quit()

    ### Update ###
    def updateStep(self):
        if len(self.undoStates) >= UNDO_HISTORY_LENGTH:
            self.undoStates.popleft()
        self.undoStates.append(SavedState(self.gamestate.cells))

        self.gamestate.updateCells()
        self.removeDeadCells()
        self.addNewCells()

    def popQueuedInput(self, block):
        f, args = self.inputQueue.get(block)
        if len(args) == 2: # event input
            f(self, args[1])
        else: # button press
            f(self)
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
                    if now - self.lastUpdate >= UPDATE_FREQS[self.update_freq_idx]:
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

    @queueInput
    def toggleGameUpdates(self):
            self.gamestate.running = not self.gamestate.running

    @queueInput
    def saveState(self):
        self.lastSavedState = SavedState(self.gamestate.cells)

    @queueInput
    def saveStateToFile(self):
        filename = filedialog.asksaveasfilename(initialdir=__file__, title="Select state file", filetypes=(("text", "*.txt"), ("all files", "*.*")))
        if filename:
            with open(filename, 'w') as fd:
                for cell in self.gamestate.cells:
                    fd.write(f"{cell[0]},{cell[1]}\n")

    @queueInput
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

    def updateSpeedLabel(self):
        self.speedStringVar.set(f"Speed: x{self.update_freq_idx + 1}")

    @queueInput
    def increaseSpeed(self):
        if self.update_freq_idx >= len(UPDATE_FREQS)-1: return
        self.update_freq_idx += 1
        self.updateSpeedLabel()

    @queueInput
    def decreaseSpeed(self):
        if self.update_freq_idx <= 0: return
        self.update_freq_idx -= 1
        self.updateSpeedLabel()

    ### Init ###
    def createWidgets(self):
        self.quitButton = tk.Button(self, text='Quit', command=self.quitApp, width=10)
        self.quitButton.grid(row=0, column=0, sticky="NW")

        self.gameControlFrame = tk.Frame(self)
        self.gameControlFrame.grid(row=0, column=1, sticky="NE")
        self.startButton = tk.Button(self.gameControlFrame, text='Start/Pause', command=self.toggleGameUpdates, width=10)
        self.startButton.grid(row=0, column=0)
        self.stepButton = tk.Button(self.gameControlFrame, text='Step', command=self.manualStep, width=10)
        self.stepButton.grid(row=0, column=1)
        self.stepButton = tk.Button(self.gameControlFrame, text='Step back', command=self.manualStepBack, width=10)
        self.stepButton.grid(row=0, column=2)
        self.speedStringVar = tk.StringVar()
        self.updateSpeedLabel()
        self.speedLabel = tk.Label(self.gameControlFrame, textvariable=self.speedStringVar)
        self.speedLabel.grid(row=1, column=0)
        self.speedIncreaseButton = tk.Button(self.gameControlFrame, text='Faster', command=self.increaseSpeed, width=10)
        self.speedIncreaseButton.grid(row=1, column=1)
        self.speedDecreaseButton = tk.Button(self.gameControlFrame, text='Slower', command=self.decreaseSpeed, width=10)
        self.speedDecreaseButton.grid(row=1, column=2)

        self.stateControlFrame = tk.Frame(self)
        self.stateControlFrame.grid(row=0, column=2, sticky="E")
        self.saveButton = tk.Button(self.stateControlFrame, text='Quicksave', command=self.saveState, width=10)
        self.saveButton.grid(row=0, column=0)
        self.loadButton = tk.Button(self.stateControlFrame, text='Load quicksave', command=self.loadState, width=10)
        self.loadButton.grid(row=0, column=1)
        self.loadButton = tk.Button(self.stateControlFrame, text='Clear state', command=self.clearState, width=10)
        self.loadButton.grid(row=0, column=2)
        self.saveToFileButton = tk.Button(self.stateControlFrame, text='Save to file', command=self.saveStateToFile, width=10)
        self.saveToFileButton.grid(row=1, column=0)
        self.saveToFileButton = tk.Button(self.stateControlFrame, text='Load from file', command=self.loadStateFromFile, width=10)
        self.saveToFileButton.grid(row=1, column=1)

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
    root = tk.Tk()
    app = Application(root)
    app.master.title("Game of Life")
    app.mainloop()
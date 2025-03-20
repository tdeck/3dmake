If your computer runs on Windows, you may have never used the programs Terminal or Command Prompt, but they provide a different way to manage files and run programs on your computer. This short guide is intended to help you learn what you need to use the terminal effectively with a screen reader so you can use 3DMake. 3DMake needs to be run from the terminal; and it will simply exit without doing anything if you run it by clicking on it or pressing ENTER in Windows Explorer.

First of all, what do I mean when I say "terminal"? The terminal is a window for interacting with text-based programs. Programs that run in the terminal are started by typing a line of text and hitting enter, rather than by selecting an icon on the desktop or in a file folder. The program's interactions are also in text, and they may ask you additional questions when something interactive. Such programs often work very well with a screen reader because of this text-based communication style. Sighted people using the terminal simply see a window full of lines of text that they have typed or that the programs they've run have produced. When a terminal program finishes, the window stays open and accepts the name of the next program you want to run.

## Configuring your screen reader
If you are using NVDA, I recommend changing the following settings when using terminal programs:

1. Ensure "report dynamic content changes" is on by pressing NVDA key + 5 once or twice.
2. Under your NVDA preferences, in the Speech setting, ensure that Punctuation/symbol level is set to "most" or "all".

I don't have personal experience with JAWS, but if you have trouble you might try the steps described [here](https://groups.io/g/jfw-users/topic/running_programs_in_the/101694533). If you do use the terminal with JAWS, please let me know what you recommend by emailing troy AT blindmakers.net so I can give good advice to other people.

## Opening the terminal

There are a few options for terminal programs in Windows. The nicest one is called Windows Terminal, or simply, Terminal. On Windows 10 you may not have Terminal installed, but you can use the Command Prompt program which works the same way.

To launch the Terminal program, type "Terminal" in the start menu, but don't hit enter if you find it. Instead, hit the right arrow key, then use the up and down arrows to select the "Command prompt" option, and hit enter to open that. (At this point, sometimes Windows leaves the start menu open, so you may need to ALT+TAB to get to the command prompt).

If you can't find the Terminal program, search for "cmd" which should bring up the "Comamnd Prompt" and open that instead.

You should hear something like this:

```
command prompt terminal
C:\Users\troy>
```

The last line of the command contains the complete path to the folder you're currently working in, followed by a greater than sign. In the terminal, you're always running commands from the perspective of being in some folder, just like in the File Explorer in Windows. When you first open it, you'll be in your home folder (in my case `C:\Users\troy`, which is the folder "troy" on the C drive, inside the folder "users". The current folder is also sometimes called the "working directory".

If you hit enter without typing anything, the terminal will print this same last line again (the path with the greater than sign after it). This entire line is called a "prompt" - the greater than sign is a little hint that you can type commands there, and it separates what you typed visually from what the terminal said to you. 

In the next section, we'll learn a couple of command you can issue here and what they do.

## Basic terminal commands

Before we start using 3DMake, let's talk a bit about how to navigate through folders in the terminal. In particular, let's look at how we can see what files are in the current directory, and how to change what directory we are in.

### Directory listing 
To list the files and folders inside the current directory, type the command `dir` (short for DIRectory), and hit enter. 

You will get a long list of files and folders. It may begin something like this

```
 Volume in drive C is Windows
 Volume Serial Number is 52DE-2B31

 Directory of C:\Users\troy

03/19/2025  04:17 PM    <DIR>          .
03/19/2025  04:17 PM    <DIR>          ..
01/14/2025  03:18 AM    <DIR>          Contacts
01/14/2025  03:18 AM    <DIR>          Desktop
03/15/2025  08:14 PM    <DIR>          Documents
03/17/2025  08:02 PM    <DIR>          Downloads
```

Each line has the date the file or directory was last modified, the time it was last modified, an optional `<DIR>` if that entry is actually a directory, and the name of the file or directory. At the beginning of the list you'll find the special entries `.` (dot) and `..` (dot dot). These represent the current directory and the parent directory respectively - don't worry about them right now!

Now let's say you don't want to listen to all the noise about dates and times. You can modify the `dir` command before hitting enter, by adding `/b` (space then forward slash b) after it. This will make it list only the names of the files and folders. Unfortunately, you can't easily tell what is a file and what is a folder, but often you'll remember that anyway. The "/b" stands for "bare", by the way.


### Changing directories

If you want to change to a directory that's inside the current folder, you can use the `cd` command with the name of the place you want to go (`cd` stands for "change directory"). For example, if you're in the home folder and want to go into Downloads, you can type `cd downloads` and hit enter.

In addition to going into a child folder, you can also change "up one level" into the parent folder. This is like hitting ALT + Up Arrow in the File Explorer. To change to the parent directory, type `cd ..` (cd space dot dot) and hit enter. The `..` is a special term for your parent directory. For example, if you were in C:\Users\troy and you did `cd ..`, you'd then be in `C:\Users`.

You can also provide the complete path of a folder you want to go to, if you know it. For example, if you want to go to `c:\Program Files` you can simply type `cd C:\Program Files` no matter where your current directory is. 

### Opening files and folders

The terminal can also launch normal graphical programs and edit documents, which will open in a new window. For example, if you have a file called "diary.txt", you can type `notepad diary.txt` to open it in notepad. A very useful command is `start`, which will try to figure out the best way to open a file or folder. For example `start flower.png` will open the photo in an image viewer, while `start .` will open the current directory in the file explorer (because a single dot is a shorthand for "the current directory").

### Getting help

The `help` command will list a lot of commands you can use, and what they do. To learn more about one, you can type `help` space, then the name of the command. So for example, to learn about how to use DEL to delete files, type `help del` and hit enter.

When help describes the usage of a command, it will tell you optional options in square brackets. For example, `DEL [/P] [/F]` means that you can (but don't need to) add `/P` and/or `/F` after DEL to modify how it works.

## 3DMake commands

Now that we've talked about how to navigate around in the terminal and run some commands, let's get started with 3DMake. Before this step, download 3DMake and extract/unzip the ZIP file (you extract it in the regular file explorer by selecting it, hitting Shift+F10 to open the menu, and selecting "Extract All"). Pay attention to what folder you put 3DMake in, and make sure it's easy to get to. For this example, let's say it's in Downloads.

### First time setup 

The first time you run 3DMake, you'll need to go into the folder where you extracted it. This is why it's useful to know the `cd` commands. Use `cd` to get into the 3dmake_windows folder where Windows put your files when it extracted them. Then `cd` into the child folder called `3dmake`.

At this point, in the `3dmake` folder, there is a program called `3dm.exe` and you can run it in the terminal by typing commands that begin with the word `3dm`. The first command is `3dm setup`, which will walk you through setting up 3DMake for the first time.

Once you have completed `3dm setup`, 3DMake will now be installed and you can run `3dm` commands from anywhere, without being inside the 3dmake folder.

### Your first steps with 3DMake 

To test your installation, let's go into another folder. Type `cd C:\Users` and then `cd` into your own user directory. Then run `3dm help` - this will give you a list of 3dm commands that you can run. If it worked, you're all set. 

Some things you could try next:

- Download a 3D model from a place like [tactiles.eu](https://tactiles.eu), [Thingiverse](https://thingiverse.com). or [Printables](https://printables.com). Then use the `3dm info` command with the model's STL file to describe it (e.g. `3dm info modelname.stl`).

- Create a new empty 3DMake project with `3dm new`, then run `3dm edit-model` and start coding up a shape in OpenSCAD. [Here is a good tutorial](https://accessible3d.io/learn-openscad-the-ultimate-guide-to-accessible-3d-design-for-blind-and-sighted-users/) to get you started.

More functions of 3DMake are described in [the main README](../README.md)

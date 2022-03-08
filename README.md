# comix-neo

Another version of "comix", a tools to backup your Comixology comics and manga!

**Disclaimer**<br />
I'm not advocating the use to pirate stuff, this tools only helps you to backup your comics into your disk only in the highest quality possible!

## Requirements
- Python 3.7+
- [Poetry](https://python-poetry.org/docs/)
- Git

The main thing you need is Poetry, this repository use poetry to manage it's dependencies.

## Installation and Preparation
1. Install [Poetry](https://python-poetry.org/docs/) if you haven't
2. Clone this repository
3. Enter the folder, and run `poetry install` to install all of the dependencies.
4. Try to run `poetry run cmx -h` to make sure it's properly installed.

## Usage
You can execute `poetry run cmx -h` to find out what the tools can do, I would recommend using the `list` command and log in so your account can be saved!

1. Run `poetry run cmx list -U your@email.com -P yourpassword`
2. This will show you all of your manga with the comic ID
3. Run `poetry run cmx dl comic_id`

The tools will than create a new folder named `comix_dl` where all of your files will be downloaded.

You can also use `--cbz` to export it as CBZ format.

If you want to download everything, you can use `poetry run cmx dlall` command.

## License
[MIT License](https://github.com/noaione/comix-neo/blob/master/LICENSE)

## Acknowledgements
- The original [comix](https://github.com/athrowaway2021/comix) tools

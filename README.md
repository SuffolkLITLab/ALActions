# ALActions - Github Actions for the Assembly Line project

Shared actions, used over many different [Assembly Line projets](https://suffolklitlab.org/docassemble-AssemblyLine-documentation/docs/).

## Usage

You can use the actions in repo github workflows by refering the subfolder of the desired action and
the a specific branch or tagged version you want to run:

```yml
jobs:
  my-workflow:
    ...
    steps:
      - uses: SuffolkLITLab/ALActions/pythontests@main 
```

For assembly line projects, you should refer to the `main` branch, as that will allow 
bug fixes to the actions to immediately propagate to the AssemblyLine repos.

## The Actions

### pythontest

`pythontest` sets up a python environment around the package, and runs any [`unittest` tests](https://docs.python.org/3/library/unittest.html) in the package.

#### Usage 

```yml
jobs:
  my-workflow:
    ...
    # No inputs
    steps:
      - uses: SuffolkLITLab/ALActions/pythontests@main 
```

### publish

`publish` (not yet in use) publishes a python package to pypi, and announces the publishing to a given Teams chat.

#### Usage

TODO

### Hall Monitor

`hall_monitor` checks a given docassemble server to make sure that all of the installed interviews can load their first page correctly,
acting like a hall monitor peaking through doors, but not investigating any further.

#### Usage

You will likely want to run this action on a schedule, several times a day.
You can see more about how to define this schedule in the 
[github on.schedule](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#onschedule)
documentation.

```yml
on:
  schedule:
    # Runs at 6:00am, and 18:00 (6:00pm)
    - cron: "0 6,18 * * *"

jobs:
  my-workflow:
    ...
    steps:
      - uses: SuffolkLITLab/ALActions/hall_monitor@main
        with:
          SERVER_URL: "https://my-docassemble.example.com"
```

## Development Details

Using [codeql-action](https://github.com/github/codeql-action) as
a template for this repo.

This repo is mostly composite actions, as opposed to javascript or docker actions for now.
Visit [Github's documentation on composite actions](https://docs.github.com/en/actions/creating-actions/creating-a-composite-action) for more info.

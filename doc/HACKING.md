
# -*- mode: markdown ; coding: utf-8 -*-

HACKING
=======

Hack on whatever you like. Ticket are [here][trac]. If you're doing something
big that doesn't have a ticket, you should probably make one. If you don't
want to register for a Trac account, you can use the ```cypherpunks``` account
with password ```writecode```.

## Generating bridge descriptors

Developers wishing to test BridgeDB will need to generate mock bridge
descriptors. This is accomplished through the file **create-descriptors**.  To
generate 20 bridge descriptors, change to the bridgedb running directory and do:

    $ ./scripts/create-descriptors 20

It is recommended that you generate at least 250 descriptors for testing.
Ideally, even more descriptors should be generated, somewhere in the realm of
2000, as certain bugs do not emerge until BridgeDB is processing thousands of
descriptors.

## Git Workflow

See this article on git branching [workflow][workflow]. The only modifications
we make are:

  * Tagging is done in the ```release-*``` branches, rather than in master.
  * It's okay to use either the ```feature/*``` and ```fix/*``` branch naming
    scheme, or follow little-t Tor's branch naming scheme,
    i.e. ```bug666-description-r1```.

## Making a release

### Updating dependencies

We maintain three requirements.txt files:

* requirements.txt (for BridgeDB)
* .travis.requirements.txt (for Travis CI)
* .test.requirements.txt (for unit tests)

Each of these files contains pinned dependencies, which are guaranteed to work
for a given release.  Before releasing a new version of BridgeDB, we should
update our dependencies.  The tool [pur][pur] (available through pip) helps us
with this.  It checks a given requirements.txt file and updates each dependency
to its latest version:

    pur -r REQUIREMENTS_FILE

### Bumping the version number

Bumping the version number at release time (which, for BridgeDB really means
deploy time, as of right now) means doing the following:

    $ git checkout develop
    [merge some fix/bug/feature/etc branches]
    $ git checkout -b release-0.0.2 develop
    $ git tag -a -s bridgedb-0.0.2
    [pip maintainance commands *would* go here, if we ever have any]
    $ git checkout master
    $ git merge -S --no-ff release-0.0.2
    $ git checkout develop
    $ git merge -S --no-ff master
    $ git push <remote> master develop

And be sure not to forget to do:

    $ git push --tags

If the currently installed version is *not* from one of the signed tags, the
version number attribute created by versioneer will be the short ID of the git
commit from which the installation took place, prefixed with the most recent
tagged release at that point, i.e.:

    >>> import bridgedb
    >>> bridgedb.__version__
    0.0.1-git528ff30c

References
----------
[trac]: https://trac.torproject.org/projects/tor/query?status=!closed&component=Circumvention%2FBridgeDB
[workflow]: https://nvie.com/posts/a-successful-git-branching-model/
[pur]: https://pypi.org/project/pur/

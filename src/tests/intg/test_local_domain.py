#
# SSSD LOCAL domain tests
#
# Copyright (c) 2015 Red Hat, Inc.
# Author: Michal Zidek <mzidek@redhat.com>
#
# This is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 only
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import os
import stat
import pwd
import grp
import time
import config
import signal
import subprocess
import pytest
import ent
from util import unindent


def stop_sssd():
    pid_file = open(config.PIDFILE_PATH, "r")
    pid = int(pid_file.read())
    os.kill(pid, signal.SIGTERM)
    while True:
        try:
            os.kill(pid, signal.SIGCONT)
        except:
            break
        time.sleep(1)


def create_conf_fixture(request, contents):
    """Generate sssd.conf and add teardown for removing it"""
    conf = open(config.CONF_PATH, "w")
    conf.write(contents)
    conf.close()
    os.chmod(config.CONF_PATH, stat.S_IRUSR | stat.S_IWUSR)
    request.addfinalizer(lambda: os.unlink(config.CONF_PATH))


def create_sssd_fixture(request):
    """Start sssd and add teardown for stopping it and removing state"""
    if subprocess.call(["sssd", "-D", "-f"]) != 0:
        raise Exception("sssd start failed")

    def teardown():
        try:
            stop_sssd()
        except:
            pass
        subprocess.call(["sss_cache", "-E"])
        for path in os.listdir(config.DB_PATH):
            os.unlink(config.DB_PATH + "/" + path)
        # FIXME: Uncomment this when ticket #2726 is solved
        # https://fedorahosted.org/sssd/ticket/2726
        # for path in os.listdir(config.MCACHE_PATH):
        #     os.unlink(config.MCACHE_PATH + "/" + path)
    request.addfinalizer(teardown)


@pytest.fixture
def local_domain_only(request):
    conf = unindent("""\
        [sssd]
        domains             = LOCAL
        services            = nss

        [nss]
        memcache_timeout = 0

        [domain/LOCAL]
        id_provider         = local
        min_id = 10000
        max_id = 20000
    """).format(**locals())
    create_conf_fixture(request, conf)
    create_sssd_fixture(request)
    return None


def assert_nonexistent_user(name):
    with pytest.raises(KeyError):
        pwd.getpwnam(name)


def assert_nonexistent_group(name):
    with pytest.raises(KeyError):
        grp.getgrnam(name)


def test_wrong_LC_ALL(local_domain_only):
    """
    Regression test for ticket
    https://fedorahosted.org/sssd/ticket/2785

    """
    subprocess.check_call(["sss_useradd", "foo", "-M"])
    pwd.getpwnam("foo")

    # Change the LC_ALL variable to nonexistent locale
    oldvalue = os.environ.get("LC_ALL", "")
    os.environ["LC_ALL"] = "nonexistent_locale"

    # sss_userdel must remove the user despite wrong LC_ALL
    subprocess.check_call(["sss_userdel", "foo", "-R"])
    assert_nonexistent_user("foo")
    os.environ["LC_ALL"] = oldvalue


def test_sss_group_add_show_del(local_domain_only):
    """
    Regression test for tickets
    https://fedorahosted.org/sssd/ticket/3173
    https://fedorahosted.org/sssd/ticket/3175
    """

    subprocess.check_call(["sss_groupadd", "foo", "-g", "10001"])

    "This should not raise KeyError"
    ent.assert_group_by_name("foo", dict(name="foo", gid=10001))

    "sss_grupshow should return 0 with existing group name"
    subprocess.check_call(["sss_groupshow", "foo"])

    subprocess.check_call(["sss_groupdel", "foo"])
    assert_nonexistent_group("foo")

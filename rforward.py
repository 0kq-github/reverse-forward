#!/usr/bin/env python

# Copyright (C) 2008  Robey Pointer <robeypointer@gmail.com>
#
# This file is part of paramiko.
#
# Paramiko is free software; you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation; either version 2.1 of the License, or (at your option)
# any later version.
#
# Paramiko is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Paramiko; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA.

"""
Sample script showing how to do remote port forwarding over paramiko.

This script connects to the requested SSH server and sets up remote port
forwarding (the openssh -R option) from a remote port through a tunneled
connection to a destination reachable from the local machine.
"""


import socket
import select
import datetime
import threading
import base64
import os
import sys
import subprocess
import sqlite3

import paramiko


class ReverseForward():
    def __init__(self, SSH_PORT,SSH_ADDRESS, LOCAL_PORT, dbname, USERNAME, KEY_FILE, key):
        self.SSH_PORT = SSH_PORT
        #DEFAULT_PORT = 4000

        self.SSH_ADDRESS = SSH_ADDRESS
        self.LOCAL_PORT = LOCAL_PORT
        self.dbname = dbname
        
        conn = sqlite3.connect(dbname)
        cur = conn.cursor()
        self.REMOTE_PORT = cur.execute("SELECT remoteport from data").fetchall()[0][0]
        self.USERNAME = USERNAME
        self.KEY_FILE = KEY_FILE

        with open(self.KEY_FILE,mode="w",encoding="utf-8") as f:
            f.write(key)
        self.g_verbose = True

        def missing_host_key(*args):
            ...
        paramiko.WarningPolicy.missing_host_key = missing_host_key

    def lprint(self, *text:str):
        """
        [現在時刻] text
        の形式でprint
        """
        text = [v for v in map(lambda x:str(x),text)]
        datime_now = datetime.datetime.now().strftime('%Y/%m/%d-%H:%M:%S')
        print(f"[{datime_now}] {' '.join(text)}")


    def handler(self, chan, host, port):
        sock = socket.socket()
        try:
            sock.connect((host, port))
        except Exception as e:
            self.verbose("エラー サーバーは起動していますか？")
            return

        self.verbose(
            f"接続 {chan.origin_addr[0]}:{chan.origin_addr[1]} -> {host}:{port}"
        )
        while True:
            r, w, x = select.select([sock, chan], [], [])
            if sock in r:
                data = sock.recv(1024)
                if len(data) == 0:
                    break
                chan.send(data)
            if chan in r:
                data = chan.recv(1024)
                if len(data) == 0:
                    break
                sock.send(data)
        chan.close()
        sock.close()
        self.g_verbose = True
        self.verbose(f"切断 {chan.origin_addr[0]}:{chan.origin_addr[1]}")


    def reverse_forward_tunnel(self, server_port, remote_host, remote_port, transport):
        transport.request_port_forward("", server_port)
        while True:
            chan = transport.accept(1000)
            if chan is None:
                continue
            thr = threading.Thread(
                target=self.handler, args=(chan, remote_host, remote_port)
            )
            thr.setDaemon(True)
            thr.start()


    def verbose(self,s):
        if self.g_verbose:
            self.lprint(s)


    HELP = """\
    Set up a reverse forwarding tunnel across an SSH server, using paramiko. A
    port on the SSH server (given with -p) is forwarded across an SSH session
    back to the local machine, and out to a remote site reachable from this
    network. This is similar to the openssh -R option.
    """


    def get_host_port(self,spec, default_port):
        "parse 'hostname:22' into a host and port, with the port optional"
        args = (spec.split(":", 1) + [default_port])[:2]
        args[1] = int(args[1])
        return args[0], args[1]


    def main(self):
        #options, server, remote = parse_options()

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.WarningPolicy())

        self.verbose("接続中...")
        try:
            client.connect(
                self.SSH_ADDRESS,
                self.SSH_PORT,
                username=self.USERNAME,
                key_filename=self.KEY_FILE
            )
        except Exception as e:
            print(f"接続に失敗しました {e}")
            os.remove(self.KEY_FILE)
            sys.exit(1)

        self.verbose(
            f"公開に成功しました {self.SSH_ADDRESS}:{self.REMOTE_PORT}"
        )
        subprocess.run(["title",f"{self.SSH_ADDRESS}:{self.REMOTE_PORT}"],shell=True)
        os.remove(self.KEY_FILE)
        try:
            self.reverse_forward_tunnel(self.REMOTE_PORT, "localhost", self.LOCAL_PORT, client.get_transport())
        except KeyboardInterrupt:
            sys.exit(0)


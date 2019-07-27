#!/usr/bin/env python3

#####
# mb2md.py v0.1 by Aaron Gallagher
# v0.2 - patches by Jon Schewe
# v0.3 - conversion to python3 by James Linder
#####

import optparse
import os
import re
import sys
import time


def trap_ioerror(func, filename, *a, **kw):
    try:
        return func(filename, *a, **kw)
    except (OSError, IOError) as e:
        print(f'{func.__name__} {filename}: {os.strerror(e.errno)}', file=sys.stderr)
        raise SystemExit(1)


def main():
    parser = optparse.OptionParser()
    parser.add_option('-i', '--infile', dest='infile', default='-',
        help='input mailbox file (defaults to stdin)', metavar='MAILBOX')
    parser.add_option('-o', '--outdir', dest='outdir',
        help="output maildir (doesn't need to exist)", metavar='MAILDIR')
    parser.add_option('--dirperm', dest='dirperm',
        help='permissions for created directories (default 0700)', 
        metavar='FLAGS')
    parser.add_option('--fileperm', dest='fileperm',
        help='permissions for created files (default 0644)', metavar='FLAGS')
    options, args = parser.parse_args()

    if not options.outdir:
        print('no output directory given', file=sys.stderr)
        sys.exit(1)

    if not options.dirperm:
        dirperm = 0o700
    else:
        try:
            dirperm = int(options.dirperm, 8)
        except ValueError:
            print(f'bad file mode: {options.dirperm}', file=sys.stderr)
            sys.exit(1)
    if not options.fileperm:
        fileperm = 0o644
    else:
        try:
            fileperm = int(options.fileperm, 8)
        except ValueError:
            print(f'bad file mode: {options.fileperm}', file=sys.stderr)
            sys.exit(1)

    if options.infile == '-':
        infile = sys.stdin
    else:
        infile = trap_ioerror(open, options.infile, 'rb')

    if not os.path.exists(options.outdir):
        trap_ioerror(os.mkdir, options.outdir)
        trap_ioerror(os.chmod, options.outdir, dirperm)
    elif not os.path.isdir(options.outdir):
        print(f'{options.outdir} is not a directory', file=sys.stderr)
        sys.exit(1)
    for dir_name in ('cur', 'new', 'tmp'):
        dir_name = os.path.join(options.outdir, dir_name)
        if not os.path.exists(dir_name):
            trap_ioerror(os.mkdir, dir_name)
            trap_ioerror(os.chmod, dir_name, dirperm)
        elif not os.path.isdir(dir_name):
            print(f'{dir_name} is not a directory', file=sys.stderr)
            sys.exit(1)
    maildir = os.path.join(options.outdir, 'cur')

    imap_uidl = last_uidl = None
    uidl_list = []
    uidl_message = None
    prev_line_empty = True
    in_headers = False
    outfile = out_filename = out_path = matime = None
    message_count = 0
    for line in infile:
        if prev_line_empty and line.startswith(b'From '):
            in_headers = True
            headers, flags, subject, uidl = [], b'', b'', None
            if outfile:
                outfile.close()
                trap_ioerror(os.utime, out_path, matime)
            line = line[5:]
            if b'@' in line:
                address_index = line.index(b' ', line.index(b'@'))
            else:
                address_index = line.index(b' ')
            from_address = line[:address_index]
            receive_date = line[address_index + 1:].strip()
            try:
                matime = time.mktime(time.strptime(
                    receive_date,
                    '%a %b %d %H:%M:%S %Y',
                ))
            except:
                matime = None
            else:
                matime = matime, matime
        elif in_headers:
            line = line.rstrip(b'\n')
            if not line:
                in_headers = False
                out_filename = '%d.%06d.mbox:2,' % (time.time(), message_count)
                if b'F' in flags:
                    out_filename += 'F'
                if b'A' in flags:
                    out_filename += 'R'
                if b'R' in flags:
                    out_filename += 'S'
                if b'D' in flags:
                    out_filename += 'T'
                out_path = os.path.join(maildir, out_filename)
                outfile = trap_ioerror(open, out_path, 'wb')
                trap_ioerror(os.chmod, out_path, fileperm)
                headers.append(b'\n')
                outfile.write(b'\n'.join(headers))
                message_count += 1
                if subject.startswith(
                        b"DON'T DELETE THIS MESSAGE -- FOLDER INTERNAL DATA"):
                    uidl_message = out_path
                continue
            headers.append(line)
            if line.startswith(b'Status: '):
                flags += line[8:]
            elif line.startswith(b'X-Status: '):
                flags += line[10:]
            elif line.startswith(b'X-Mozilla-Status: '):
                try:
                    status_flags = int(line[18:], 16)
                except ValueError:
                    continue
                if status_flags & 1:
                    flags += b'R'
                if status_flags & 2:
                    flags += b'A'
                if status_flags & 8:
                    flags += b'D'
            elif line.startswith(b'Subject: '):
                subject = line[9:]
            elif line.startswith(b'X-UID: '):
                uidl_list.append(b'%s %s' % (line[7:], bytes(out_filename, 'utf-8')))
            elif line.startswith(b'X-IMAP: ') and not uidl_message:
                m = re.match(b'X-IMAP: ([0-9]+) ([0-9]+)', line)
                if not m:
                    continue
                try:
                    imap_uidl, last_uidl = [int(i) for i in m.groups()]
                except ValueError:
                    continue
                else:
                    last_uidl += 1
        elif outfile:
            if line.startswith(b'> From'):
                line = line[1:]
            outfile.write(line)
            prev_line_empty = line == b'\n'

    if imap_uidl:
        uid_filename = os.path.join(options.outdir, 'dovecot-uidlist')
        uid_file = trap_ioerror(open, uid_filename, 'wb')
        uidl_list.insert(0, b'1 %d %d' % (imap_uidl, last_uidl))
        uidl_list.append(b'')
        uid_file.write(b'\n'.join(uidl_list))
        uid_file.close()
        trap_ioerror(os.chmod, uid_filename, fileperm)

    if outfile:
        outfile.close()
        trap_ioerror(os.utime, out_path, matime)

    if uidl_message:
        trap_ioerror(os.unlink, uidl_message)
        message_count -= 1

    print(f'{message_count} messages processed.')
    if uidl_message:
        print('(after dropping the folder internal data message)')
    print()


if __name__ == '__main__':
    main()

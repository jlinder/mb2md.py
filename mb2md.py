#!/usr/bin/env python

#####
# mb2md.py v0.1 by Aaron Gallagher
# v0.2 - patches by Jon Schewe
#####

import sys, re, optparse, os, time

def trap_ioerror(func, filename, *a, **kw):
    try:
        return func(filename, *a, **kw)
    except (OSError, IOError), e:
        print >> sys.stderr, '%s %s: %s' % (
            func.__name__, filename, os.strerror(e.errno))
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
        print >> sys.stderr, 'no output directory given'
        sys.exit(1)
    
    if not options.dirperm:
        dirperm = 0700
    else:
        try:
            dirperm = int(options.dirperm, 8)
        except ValueError:
            print >> sys.stderr, 'bad file mode: %s' % options.dirperm
            sys.exit(1)
    if not options.fileperm:
        fileperm = 0644
    else:
        try:
            fileperm = int(options.fileperm, 8)
        except ValueError:
            print >> sys.stderr, 'bad file mode: %s' % options.fileperm
            sys.exit(1)
    
    if options.infile == '-':
        infile = sys.stdin
    else:
        infile = trap_ioerror(open, options.infile)
    
    if not os.path.exists(options.outdir):
        trap_ioerror(os.mkdir, options.outdir)
        trap_ioerror(os.chmod, options.outdir, dirperm)
    elif not os.path.isdir(options.outdir):
        print >> sys.stderr, '%s is not a directory' % options.outdir
        sys.exit(1)
    for dir in ('cur', 'new', 'tmp'):
        dir = os.path.join(options.outdir, dir)
        if not os.path.exists(dir):
            trap_ioerror(os.mkdir, dir)
            trap_ioerror(os.chmod, dir, dirperm)
        elif not os.path.isdir(dir):
            print >> sys.stderr, '%s is not a directory' % dir
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
        if prev_line_empty and line.startswith('From '):
            in_headers = True
            headers, flags, subject, uidl = [], '', '', None
            if outfile:
                outfile.close()
                trap_ioerror(os.utime, out_path, matime)
            line = line[5:]
            if '@' in line:
                address_index = line.index(' ', line.index('@'))
            else:
                address_index = line.index(' ')
            from_address = line[:address_index]
            receive_date = line[address_index + 1:].strip()
            try:
                matime = time.mktime(time.strptime(receive_date, 
                    '%a %b %d %H:%M:%S %Y'))
            except:
                matime = None
            else:
                matime = matime, matime
        elif in_headers:
            line = line.rstrip('\n')
            if not line:
                in_headers = False
                out_filename = '%d.%06d.mbox:2,' % (time.time(), message_count)
                if 'F' in flags:
                    out_filename += 'F'
                if 'A' in flags:
                    out_filename += 'R'
                if 'R' in flags:
                    out_filename += 'S'
                if 'D' in flags:
                    out_filename += 'T'
                out_path = os.path.join(maildir, out_filename)
                outfile = trap_ioerror(open, out_path, 'wb')
                trap_ioerror(os.chmod, out_path, fileperm)
                headers.append('\n')
                outfile.write('\n'.join(headers))
                message_count += 1
                if subject.startswith(
                        "DON'T DELETE THIS MESSAGE -- FOLDER INTERNAL DATA"):
                    uidl_message = out_path
                continue
            headers.append(line)
            if line.startswith('Status: '):
                flags += line[8:]
            elif line.startswith('X-Status: '):
                flags += line[10:]
            elif line.startswith('X-Mozilla-Status: '):
                try:
                    status_flags = int(line[18:], 16)
                except ValueError:
                    continue
                if status_flags & 1:
                    flags += 'R'
                if status_flags & 2:
                    flags += 'A'
                if status_flags & 8:
                    flags += 'D'
            elif line.startswith('Subject: '):
                subject = line[9:]
            elif line.startswith('X-UID: '):
                uidl_list.append('%s %s' % (line[7:], out_filename))
            elif line.startswith('X-IMAP: ') and not uidl_message:
                m = re.match('X-IMAP: ([0-9]+) ([0-9]+)', line)
                if not m:
                    continue
                try:
                    imap_uidl, last_uidl = [int(i) for i in m.groups()]
                except ValueError:
                    continue
                else:
                    last_uidl += 1
        elif outfile:
            if line.startswith('> From'):
                line = line[1:]
            outfile.write(line)
            prev_line_empty = line == '\n'
    
    if imap_uidl:
        uid_filename = os.path.join(options.outdir, 'dovecot-uidlist')
        uid_file = trap_ioerror(open, uid_filename, 'wb')
        uidl_list.insert(0, '1 %d %d' % (imap_uidl, last_uidl))
        uidl_list.append('')
        uid_file.write('\n'.join(uidl_list))
        uid_file.close()
        trap_ioerror(os.chmod, uid_filename, fileperm)
    
    if outfile:
        outfile.close()
        trap_ioerror(os.utime, out_path, matime)
    
    if uidl_message:
        trap_ioerror(os.unlink, uidl_message)
        message_count -= 1
    
    print '%d messages processed.' % message_count,
    if uidl_message:
        print '(after dropping the folder internal data message)'
    print

if __name__ == '__main__':
    main()

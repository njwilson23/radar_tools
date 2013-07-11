""" Contains the `Survey` class, which is the overarching `irlib` structure.
`Survey` classes handle interaction with the raw HDF datasets, and spawn off
`Gather` classes for analysis. Each HDF dataset can be opened as a `Survey`,
which stores file references and collects metadata in the form of a
`FileHandler`. Radar lines can be created from a `Survey` using the
`ExtractLine` method, which returns a `Gather`. """


import os
import sys
import cPickle
import h5py
import numpy as np

from irlib.gather import CommonOffsetGather
from irlib.recordlist import RecordList, ParseError
from irlib.autovivification import AutoVivification

class Survey:
    """ Surveys can be broken down into **Gathers** and *traces*. To create a
    survey and extract a gather, do something like::

        # Create the survey
        S = Survey("mysurvey.h5")

        # Create the gather (Line)
        linenumber = 0      # This can be any nonzero integer
        datacapture = 0     # This corresponds to the channel frequency in
                            # dualdar setups
        L = S.ExtractLine(linenumber, dc=datacapture)

        # To see what can be done with `L`, refer to the `CommonOffsetGather
        # documentation
    """

    def __init__(self, datafile):
        """ Instantiate a **Survey** object. A survey encompasses one HDF5 file
        generated from Blue System Inc. IceRadar software.

        Parameters
        ----------
        datafile : file path to a HDF file generated by Blue Systems IceRadar
                   [string]
        """
        self.datafile = datafile
        # Create 2-level boolean map of the dataset
        self._openh5()
        try:
            self.retain = AutoVivification()
            for line in self.f:
                if isinstance(self.f[line], h5py.Group):
                    for location in list(self.f[line]):
                        self.retain[line][location] = True
        except IOError:
            sys.stdout.write("No survey exists with the" +
                             " filename:\n\t{0}\n".format(datafile))
        finally:
            self._closeh5()
        return

    def __del__(self):
        if self.status == 'open':
            self._closeh5()
        return

    def __repr__(self):
        return self.status + " survey object: " + self.datafile

    def _openh5(self, mode='r'):
        """ Open the reference H5 dataset. """
        self.f = h5py.File(self.datafile, mode)
        self.status = 'open'
        return

    def _closeh5(self):
        """ Close the reference HDF5 dataset. """
        self.f.close()
        self.status = 'closed'
        return

    def _getdatasets(self, line=None):
        """ Return a list of datasets.

        Parameters
        ----------
        line : (optional) specify a line number [integer]
        """
        if isinstance(line, int):
            path = 'line_{0}/'.format(line)
        else:
            path = '/'
        names = []
        self._openh5()
        try:
            self.f[path].visit(names.append)
            datasets = []
            for name in names:
                if (type(self.f[name]) == h5py.Dataset) and \
                  ('picked' not in self.f[path][name].name):
                    datasets.append(path+name)
        except Exception as e:
            raise e
        finally:
            self._closeh5()
        return datasets

    def _path2fid(self, path, linloc_only = False):
        """ Based on a path, return a unique FID for database
        relations. """
        try:
            # Index from [1:] to cut out any '/' that might be present
            # Line number
            lin = int(path[1:].split('/',1)[0].split('_',1)[1])
            # Location number
            loc = int(path[1:].split('/',2)[1].split('_',1)[1])
            if not linloc_only:
                # Datacapture number
                dc = int(path[1:].split('/',3)[2].split('_',1)[1])
                # Echogram number
                eg = int(path[1:].split('/',3)[2].split('_',1)[1])
            else:
                dc = 0
                eg = 0
            fid = str(lin).rjust(4,'0') + str(loc).rjust(4,'0') \
                + str(dc).rjust(4,'0') + str(eg).rjust(4,'0')
            return fid
        except Exception as e:
            sys.stderr.write('survey: failed at path2fid')
            raise e

    def GetLines(self):
        """ Return a list of the lines contained within the survey. """
        self._openh5()
        try:
            lines = [name for name in self.f.keys() if name[:4] == 'line']
        except Exception as e:
            raise e
        finally:
            self._closeh5()
        lines.sort(key=(lambda s: int(s.split('_')[1])))
        return lines

    def GetChannelsInLine(self, lineno):
        """ Return the number of channels (datacaptures per location) in a
        line. If the number is not constant throughout the line, then return
        the maximum number.

        Parameters
        ----------
        lineno : line number [integer]
        """
        try:
            line = self.GetLines()[lineno]
        except IndexError:
            sys.stderr.write("lineno out of range ({0} not in {1}:{2})\n"
                    .format(lineno, 0, len(self.GetLines)))
        self._openh5()
        try:
            dclist = [self.f[line][loc].keys() for loc in self.f[line].keys()]
        except Exception as e:
            raise e
        finally:
            self._closeh5()
        return max([len(a) for a in dclist])

    def ExtractTrace(self, line, location, datacapture=0, echogram=0):
        """ Extract the values for a trace and return as a vector.

        Parameters
        ----------
        line : line number [integer]
        location : trace number [integrer]
        datacapture : (default 0) channel number [integer]
        echogram : (default 0) echogram number [integer]
        """
        path = ('line_{lin}/location_{loc}/datacapture_{dc}/'
                'echogram_{eg}'.format(lin=line, loc=location, dc=datacapture,
                                       eg=echogram))
        self._openh5()
        try:
            vec = self.f[path].value
        except Exception as e:
            raise e
        finally:
            self._closeh5()
        return vec

    def ExtractLine(self, line, bounds=(None,None), datacapture=0,
                    fromcache=False, cache_dir="cache", print_fnm=False,
                    verbose=False, gather_type=CommonOffsetGather):
        """ Extract every trace on a line. If bounds are supplied
        (min, max), limit extraction to only the range specified.
        Return a CommonOffsetGather instance.

        Parameters
        ----------
        line : line number to extract [integer]
        bounds : return a specific data slice [integer x2]
        datacapture : datacapture subset to load [integer]
        fromcache : attempt to load from a cached file [boolean]
        cache_dir : specify a cache directory [str]
        print_fnm : print the cache search path [boolean]
        """

        if fromcache:
            fnm = self.GetLineCacheName(line, dc=datacapture, cache_dir=cache_dir)
            if print_fnm:
                print fnm
            if os.path.isfile(fnm):
                with open(fnm, 'r') as f:
                    unpickler = cPickle.Unpickler(f)
                    gatherdata = unpickler.load()
                return gatherdata
            else:
                sys.stderr.write("Cached file {0} not available; loading from "
                                 "HDF\n".format(fnm))

        path = 'line_{lin}'.format(lin=line)

        # Separate out all datasets on the correct line
        names = []
        self._openh5()
        try:
            self.f[path].visit(names.append)

            # Filter out the datasets, then the correct datacaptures
            # The following is a nested filter that first keeps elements of type
            # *h5py.Dataset*, next discards picked data, and finally restricts the
            # names to the datacaptures specified by *datacapture*.
            try:
                allowed_datacaptures = ["datacapture_{0}".format(dc)
                                        for dc in datacapture]
            except TypeError:
                allowed_datacaptures = ["datacapture_{0}".format(datacapture)]
            datasets = filter(lambda c: c.split('/')[-2] in allowed_datacaptures,
                        filter(lambda b: 'picked' not in self.f[path][b].name,
                        filter(lambda a: isinstance(self.f[path][a], h5py.Dataset),
                        names)))
            if len(datasets) == 0:
                sys.stderr.write("no datasets match the specified channel(s)\n")

            # Sort the datasets by location number
            try:
                datasets.sort(key=(lambda s: int(s.split('/')[0].split('_')[1])))
            except Exception as e:
                sys.stderr.write("Error sorting datasets by "
                                 "location number in ExtractLine()\n")
                raise e

            # If bounds are specified, slice out the excess locations
            try:
                if bounds[1] != None:
                    datasets = datasets[:bounds[1]]
                if bounds[0] != None:
                    datasets = datasets[bounds[0]:]
            except TypeError:
                sys.stderr.write("bounds kwarg in ExtractLine() "
                                 "must be a two element list or tuple\n")

            # Grab XML metadata
            metadata = RecordList(self.datafile)
            for trace in datasets:
                full_path = path + '/' + trace
                try:
                    metadata.AddDataset(self.f[path][trace],
                                        fid=self._path2fid(full_path))
                except ParseError as e:
                    sys.stderr.write(e.message + '\n')
                    metadata.CropRecords()

            # Create a single numpy array of data
            # Sometimes the number of samples changes within a line. When this
            # happens, pad the short traces with zeros.
            line_ptr = self.f[path]
            nsamples = [line_ptr[dataset].shape[0] for dataset in datasets]
            try:
                maxsamples = max(nsamples)
                arr = np.zeros((maxsamples, len(datasets)))
                for j, dataset in enumerate(datasets):
                    arr[:nsamples[j],j] = line_ptr[dataset].value
            except ValueError:
                sys.stderr.write("Failed to index {0} - it might be "
                                 "empty\n".format(path))
                return

        except Exception as e:
            raise e
        finally:
            self._closeh5()

        return CommonOffsetGather(arr, infile=self.datafile, line=line,
                metadata=metadata, retain=self.retain['line_{0}'.format(line)],
                dc=datacapture)

    def GetLineCacheName(self, line, dc=0, cache_dir="cache"):
        """ Return a standard cache name.

        Parameters
        ----------
        line : line number [integer]
        dc : datacapture number [integer]
        cache_dir : (default `cache/`) cache directory [string]
        """
        cnm = os.path.join(cache_dir,
                os.path.splitext(os.path.basename(self.datafile))[0] + \
                '_line' + str(line) + '_' + str(dc) + '.ird')
        return cnm

    def WriteHDF5(self, fnm, overwrite=False):
        """ Given a filename, write the contents of the original file to a
        new HDF5 wherever self.retain is True. The usage case for this is
        when bad data have been identified in the original file.

        Note that for now, this does not preserve HDF5 object comments.

        Parameters
        ----------
        fnm : file path [string]
        overwrite : (dafault `False`) overwrite existing file [boolean]
        """
        if os.path.exists(fnm) and not overwrite:
            print 'already exists'
            return

        with h5py.File(fnm, 'w') as fout:

            for line in self.f:
                if isinstance(self.f[line], h5py.Group):
                    try:
                        fout.create_group(line)
                    except ValueError:
                        raise Exception("somehow, {0} already existed in "
                                        "Survey.WriteHDF5(). This might be a "
                                        "problem, and you should look into "
                                        "it.". format(line))
                    print "\t{0}".format(line)
                    for location in list(self.f[line]):
                        if self.retain[line][location]:
                            self.f.copy('{0}/{1}'.format(line, location),
                                        fout[line])
        return


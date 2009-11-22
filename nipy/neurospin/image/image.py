"""
Image class. 

Here, image means a real-valued mapping from a regular 3D lattice. It
can be masked or not.
"""

import numpy as np
from scipy import ndimage

import nipy.io.imageformats as brifti


# Globals
_def_cval = 0 
_def_order = 1 
_def_optimize = False

# class `Grid`
class Grid(object): 
    """ An object to represent a regular 3d grid, or sub-grid.

    Attributes
    ----------
    shape: tuple of ints
        Shape of the grid, e.g., ``(256,256,124)``

    corner: tuple of ints, optional
        Grid coordinates of the sub-grid corner

    spacing: tuple of ints, optional
        Subsampling factors 

    affine: ndarray 
        4x4 affine matrix that maps the grid coordinates to some
        coordinate system.
    
    """
    def __init__(self, shape, corner=(0,0,0), spacing=(1,1,1), affine=None):

        if not len(shape) == 3:
            raise ValueError('The specified shape should be of length 3.')
        if not len(corner) == 3:
            raise ValueError('The specified corner should be of length 3.')
        if not len(spacing) == 3:
            raise ValueError('The specified subsampling factors should be of length 3.')
        self._shape = np.array(shape[0:3], dtype='uint')
        self._corner = np.array(corner[0:3], dtype='uint')
        self._spacing = np.array(spacing[0:3], dtype='uint')
        self._affine = affine

    def _get_shape(self):
        return self._shape

    def _get_corner(self):
        return self._corner

    def _get_spacing(self):
        return self._spacing
    
    def coords(self):
        c = self._corner
        s = self._shape
        sp = self._spacing
        x,y,z = np.mgrid[c[0]:c[0]+s[0]:sp[0],
                         c[1]:c[1]+s[1]:sp[1],
                         c[2]:c[2]+s[2]:sp[2]]
        x,y,z = x.ravel(),y.ravel(),z.ravel()
        if self._affine == None: 
            return x, y, z
        return apply_affine(self._affine, (x, y, z))
                   
    def slice(self, array): 
        c = self._corner
        s = self._shape
        sp = self._spacing
        return array[c[0]:c[0]+s[0]:sp[0],
                     c[1]:c[1]+s[1]:sp[1],
                     c[2]:c[2]+s[2]:sp[2]]

    def __str__(self):
        return 'Grid: shape %s, corner %s, spacing %s' % (self._shape, self._corner, self._spacing) 

    shape = property(_get_shape)
    corner = property(_get_corner)
    spacing = property(_get_spacing)
    

# class `Block`

class Block(object): 
    """ A basic class to represent an image defined on a regular
    lattice.
    """
    def __init__(self, data, affine, world=None, cval=_def_cval): 
        self._data = data
        self._affine = affine
        self._inverse_affine = inverse_affine(affine)
        self._world = world 
        self._cval = cval 

    def _get_shape(self):
        return self._data.shape

    def _get_dtype(self): 
        return self._data.dtype

    def _get_affine(self):
        return self._affine

    def _get_inverse_affine(self):
        return self._inverse_affine

    def _get_data(self):
        """
        Get a 3d array.
        """
        return self._data

    def values(self, coords=None, grid_coords=False, dtype=None, 
               order=_def_order, optimize=_def_optimize):

        # Convert coords into a tuple of ndarrays
        tmp = [np.asarray(coords[i]) for i in range(3)]
        coords = tuple(tmp)

        # If coords are intended to describe world coordinates,
        # convert them into grid coordinates
        if not grid_coords:
            to_grid = self._inverse_affine
            if isinstance(coords, Grid): 
                # compose transforms
                if coords._affine: 
                    coords._affine = np.dot(to_grid, self._affine)
                else:
                    coords._affine = to_grid
            else: 
                coords = apply_affine(to_grid, coords)

              
        # If coords is a Grid instance, we do not need to explicitely
        # compute the coordinates
        if isinstance(coords, Grid): 
            if coords._affine:
                return resample(self._data, coords._affine,
                                order=order, dtype=dtype, 
                                cval=self._cval, optimize=optimize).squeeze()
            else:
                return coords.slice(self._data)
        
        # At this point, coords is an explicit tuple of coordinates.
        
        # Avoid interpolation if coordinates are integers.
        if [issubclass(c.dtype.type, np.integer) for c in coords].count(True):
            return self._data[coords]
        else: # interpolation needed
            return sample(self._data, coords, 
                          order=order, dtype=dtype, 
                          cval=self._cval, optimize=optimize)


    shape = property(_get_shape)
    dtype = property(_get_dtype)
    affine = property(_get_affine)
    inverse_affine = property(_get_inverse_affine)
    data = property(_get_data)


# class `Image`

class Image(object):
    """ A class representing a (real-valued???) mapping from a regular
        3D lattice.  

        Bla. 

        Attributes
        -----------
        
        Bla. 

        Notes
        ------

        Bla. 
    """
    def __init__(self, data, affine, world=None, cval=_def_cval):
        """ The base image class.

            Parameters
            ----------

            data: ndarray
                n dimensional array giving the embedded data, with the first
                three dimensions being spatial.

            affine: ndarray 
                a 4x4 transformation matrix from voxel to world.

            world: string, optional 
                An identifier for the real-world coordinate system, e.g. 
                'scanner' or 'mni'. 
            
            cval: number, optional 
                Background value (outside image boundaries).  
        """

        # TODO: Check that the mask array, if provided, is consistent
        # with the data array
        # Check array datatype and cval 
        self._shape = data.shape
        self._dtype = data.dtype
        self._masked = False
        self._block = Block(data, affine, world=world, cval=cval)
        self._mask = Grid(data.shape)
        self._affine = affine
        self._inverse_affine = inverse_affine(affine)
        self._world = world
        self._cval = cval        
        self._data = None

    def _get_masked(self):
        return self._masked

    def _get_shape(self):
        return self._shape

    def _get_dtype(self):
        return self._dtype

    def _get_affine(self):
        return self._affine

    def _get_inverse_affine(self):
        return self._inverse_affine

    def _get_data(self):
        """
        Get a 3d array.
        """
        if self._masked:
            data = np.zeros(self._shape, dtype=self._dtype)
            if not self._cval == 0:  
                data += self._cval
            if self._block: # mask is a Grid instance
                c = self._mask._corner 
                s = self._mask._shape
                sp = self._mask._spacing
                data[c[0]:c[0]+s[0]:sp[0],
                     c[1]:c[1]+s[1]:sp[1],
                     c[2]:c[2]+s[2]:sp[2]] = self._block._data
            else:
                data[self._mask] = self._data
            return data 
        else:
            return self._block._data

    def _get_mask(self):
        return self._mask 

    def putmask(self, mask): 
        """
        
        Parameters
        ----------

            mask: ndarray, optional 
                A 3xN list of coordinates
        """
        if isinstance(mask, Grid):
            # block to world affine transformation
            t_subgrid2grid = np.diag(np.concatenate((mask._spacing,[1]),1))
            t_subgrid2grid[0:3,3] = mask._corner
            affine = np.dot(self._affine, t_subgrid2grid)

            data = self._get_data()
            block = Block(mask.slice(data), affine, world=self._world, cval=self._cval)
            im = Image(data, self._affine, world=self._world, cval=self._cval)
            if im.shape == block.shape: 
                im._masked = False
            else:
                im._masked = True
            im._mask = mask 
            im._block = block
            return im 
        else:
            im = Image(self._get_data(), self._affine, world=self._world, cval=self._cval)
            im._data = im._block._data[mask]
            im._masked = True
            im._block = None 
            im._mask = mask 
            return im 


    def crop(self): 
        """
        Adjust the minimal bounding box. 
        """
        if self._block:
            data = self._block._data
            affine = self._block._affine
            return Image(data, 
                         affine, 
                         world=self._world, 
                         cval=self._cval)
        

        # Underlying mask is not a grid: define a bounding box
        corner = np.asarray([self._mask[i].min() for i in range(3)])
        shape = [1+self._mask[i].max()-corner[i] for i in range(3)]
        data = np.zeros(shape, dtype=self._dtype)
        if not self._cval == 0:  
            data += self._cval
        data[[self._mask[i]-corner[i] for i in range(3)]] = self._data
        box2im_affine = np.eye(4)
        box2im_affine[0:3,3] = corner
        affine = np.dot(self._affine, box2im_affine)
        return Image(data, affine, world=self._world, cval=self._cval)

    
    def values(self, coords=None, grid_coords=False, dtype=None, 
               order=_def_order, optimize=_def_optimize):
        """ Return interpolated values at the points specified by coords. 

            Parameters
            ----------
            coords: {ndarray, Grid}
                List of coordinates. 

            grid_coords: boolean, optional
                Determine whether the input coordinates are in the
                world or grid coordinate system. 
        
            Returns
            --------
            x: ndarray
                One-dimensional array. 

        """
        
        # If no coordinates specified, assume the image mask 
        if coords == None: 
            grid_coords = True
            if isinstance(self._mask, Grid): 
                coords = self._mask.coords()
            else: 
                coords = self._mask 

        # Case of an already exsiting block
        if self._block: 
            block = self._block
            # If coords are meant to represent grid coordinates,
            # convert them relatively to the underlying 'block'
            # subgrid
            if self._masked and grid_coords:
                coords = [coords[i]-self._mask._corner[i] for i in range(3)]
                if not self._mask._spacing.max() == 1:
                    coords = [coords[i]/float(self._mask._spacing[i]) for i in range(3)]
                coords = tuple(coords)

        # Otherwise, create block on the fly 
        else: 
            block = Block(self._get_data(), self._affine)

        return block.values(coords, grid_coords, dtype, order, optimize)


    def transform(self, transform, shape, affine):
        """
        transform: world transformation

        affine: destination grid to-world transformation. 
        """
        
        t_ = np.dot(self._inverse_affine, np.dot(inverse_affine(transform), affine))

        return resample(self._get_data(), affine=t_, shape=shape,
                        order=order, dtype=dtype, 
                        cval=self._cval, optimize=optimize)



    data = property(_get_data)
    affine = property(_get_affine)
    inverse_affine = property(_get_inverse_affine)
    mask = property(_get_mask)
    masked = property(_get_masked)
    shape = property(_get_shape)
    dtype = property(_get_dtype)


        


def apply_affine(affine, XYZ):
    """
    Parameters
    ----------
    affine: ndarray 
        A 4x4 matrix representing an affine transform. 

    coords: tuple of ndarrays 
        tuple of 3d coordinates stored row-wise: (X,Y,Z)  
    """
    tXYZ = np.array(XYZ, dtype='double')
    if tXYZ.ndim == 1: 
        tXYZ = np.reshape(tXYZ, (3,1))
    tXYZ[:] = np.dot(affine[0:3,0:3], tXYZ[:])
    tXYZ[0,:] += affine[0,3]
    tXYZ[1,:] += affine[1,3]
    tXYZ[2,:] += affine[2,3]
    return tuple(tXYZ)



def load_image(fname): 
    im = brifti.load(fname)
    return Image(im.get_data(), im.get_affine())


def save_image(Im, fname):
    im = brifti.Nifti1Image(Im.data, Im.affine)
    brifti.save(im, fname)



def sample(data, coords, order=_def_order, dtype=None, 
           cval=_def_cval, optimize=_def_optimize): 
    
    if dtype == None: 
        dtype = data.dtype

    coords = tuple(coords)
    npts = coords[0].size

    if optimize and order==3:
        from image_module import cspline_transform, cspline_sample3d
        cbspline = cspline_transform(data)
        X, Y, Z = coords
        output = np.zeros(npts, dtype='double')
        output = cspline_sample3d(output, cbspline, X, Y, Z)
        output.astype(dtype)
    else: 
        output = np.zeros(npts, dtype=dtype)
        ndimage.map_coordinates(data, 
                                np.c_[coords].T, 
                                order=order, 
                                cval=cval,
                                output=output)
        
    return output



def resample(data, affine, shape=None, order=_def_order, dtype=None, 
             cval=_def_cval, optimize=_def_optimize): 

    if shape == None:
        shape = data.shape

    if dtype == None: 
        dtype = data.dtype

    if optimize and order==3:
        from image_module import cspline_resample3d
        output = cspline_resample3d(data, 
                                    shape, 
                                    affine, 
                                    dtype=dtype)
    else: 
        output = np.zeros(data.shape, dtype=dtype)
        ndimage.affine_transform(data, 
                                 affine[0:3,0:3],
                                 offset=affine[0:3,3],
                                 output_shape=shape,
                                 order=order, 
                                 cval=cval, 
                                 output=output)

    return output 


def inverse_affine(affine):
    return np.linalg.inv(affine)


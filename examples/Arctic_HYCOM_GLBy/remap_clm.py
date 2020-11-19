import numpy as np
import os
try:
  import netCDF4 as netCDF
except:
  import netCDF3 as netCDF
import matplotlib.pyplot as plt
import time
from datetime import datetime
from matplotlib.dates import date2num, num2date

import pyroms
import pyroms_toolbox
from pyroms import _remapping
import xarray as xr
import xesmf
import pdb
from regrid_GLBy import regrid_GLBy

class nctime(object):
    pass

def remap_clm(src_file, src_varname, src_grd, dst_grd, dxy=20, cdepth=0, kk=0, dst_dir='./'):

    # get time
    nctime.long_name = 'time'
    nctime.units = 'days since 1900-01-01 00:00:00'
    # time reference "days since 1900-01-01 00:00:00"
#    ref = datetime(1900, 1, 1, 0, 0, 0)
#    ref = date2num(ref)
#    tag = src_file.rsplit('/')[-1].rsplit('_')[-2].rsplit('-')[0]
#    print tag
#    year = int(tag[:4])
#    month = int(tag[4:6])
#    day = int(tag[6:])
#    time = datetime(year, month, day, 0, 0, 0)
#    time = date2num(time)
#    time = time - ref
#    time = time + 2.5 # 5-day average
    cdf = netCDF.Dataset(src_file)
    src_var = cdf.variables[src_varname][0]
    time = cdf.variables['ocean_time'][0]


    # create IC file
    dst_file = src_file.rsplit('/')[-1]
    dst_file = dst_dir + dst_file[:-3] + '_' + src_varname + '_clim_' + dst_grd.name + '.nc'
    print('\nCreating file', dst_file)
    if os.path.exists(dst_file) is True:
        os.remove(dst_file)
    pyroms_toolbox.nc_create_roms_file(dst_file, dst_grd, nctime)

    # open IC file
    nc = netCDF.Dataset(dst_file, 'a', format='NETCDF3_64BIT')

    #load var
    cdf = netCDF.Dataset(src_file)
    src_var = cdf.variables[src_varname]

    #get missing value
    spval = src_var._FillValue
    src_var = src_var[0]

    # determine variable dimension
    #ndim = len(src_var.dimensions)
    ndim = len(src_var.shape)

    pos = 't'
    Cpos = 'rho'
    z = src_grd.z_t
    Mp, Lp = dst_grd.hgrid.mask_rho.shape
    if src_varname == 'ssh':
        dst_varname = 'zeta'
        dimensions = ('ocean_time', 'eta_rho', 'xi_rho')
        long_name = 'free-surface'
        units = 'meter'
        field = 'free-surface, scalar, series'
        vartime = 'ocean_time'
    elif src_varname == 'temp':
        dst_varname = 'temp'
        dimensions = ('ocean_time', 's_rho', 'eta_rho', 'xi_rho')
        long_name = 'potential temperature'
        units = 'Celsius'
        field = 'temperature, scalar, series'
        vartime = 'ocean_time'
    elif src_varname == 'salt':
        dst_varname = 'salt'
        dimensions = ('ocean_time', 's_rho', 'eta_rho', 'xi_rho')
        long_name = 'salinity'
        units = 'PSU'
        field = 'salinity, scalar, series'
        vartime = 'ocean_time'
    else:
        raise ValueError('Undefined src_varname')


    if ndim == 3:
        # build intermediate zgrid
        zlevel = -z[::-1,0,0]
        nzlevel = len(zlevel)
        dst_zcoord = pyroms.vgrid.z_coordinate(dst_grd.vgrid.h, zlevel, nzlevel)
        dst_grdz = pyroms.grid.ROMS_Grid(dst_grd.name+'_Z', dst_grd.hgrid, dst_zcoord)


    # create variable in file
    print('Creating variable', dst_varname)
    nc.createVariable(dst_varname, 'f8', dimensions, fill_value=spval)
    nc.variables[dst_varname].long_name = long_name
    nc.variables[dst_varname].units = units
    nc.variables[dst_varname].field = field
    nc.variables[dst_varname].time = vartime


    # remapping
    print('remapping', dst_varname, 'from', src_grd.name, \
              'to', dst_grd.name)
    print('time =', time)

    if ndim == 3:
        # flood the grid
        print('flood the grid, spval = ', spval)
        src_varz = pyroms_toolbox.Grid_HYCOM.flood_fast(src_var, src_grd, pos=pos, spval=spval, \
                                dxy=dxy, cdepth=cdepth, kk=kk)
#       flooded = xr.DataArray(src_varz)
#       flooded.to_netcdf("flooded.nc")
    else:
        src_varz = src_var

    # horizontal interpolation using xesmf
    print('horizontal interpolation using xesmf')

    dst_varz = regrid_GLBy(src_varz, method='nearest_s2d')

    if ndim == 3:
        # vertical interpolation from standard z level to sigma
        print('before vertical remap 1', dst_varz[:,928,324])
        print('before vertical remap 2', dst_varz[:,460,350])
        print('vertical interpolation from standard z level to sigma')
        dst_var = pyroms.remapping.z2roms(dst_varz[::-1,:,:], dst_grdz, \
                          dst_grd, Cpos=Cpos, spval=spval, flood=False)
        print('after vertical remap 1', dst_var[:,928,324])
        print('after vertical remap 2', dst_var[:,460,350])

    # land mask
        idxu = np.where(dst_grd.hgrid.mask_rho == 0)
        for n in range(dst_grd.vgrid.N):
            dst_var[n,idxu[0], idxu[1]] = spval
    else:
        dst_var = dst_varz

    # write data in destination file
    print('write data in destination file')
    nc.variables['ocean_time'][0] = time
    nc.variables[dst_varname][0] = dst_var

    # close destination file
    nc.close()

    if src_varname == 'ssh':
        return dst_varz

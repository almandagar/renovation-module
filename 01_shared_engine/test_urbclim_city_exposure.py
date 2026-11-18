import tempfile,unittest
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from urbclim_city_exposure_2035 import aggregate_city_rasters,INDICATORS
class TestUrbClim(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);p=Path(self.tmp.name);self.p=p
  self.zone=p/'zones.tif';self.pop=p/'population.tif';self.temp=p/'T2M_nightover20_2031-2040_CurPol_ensmean_WGS84.tif';self.uhi=p/'T2M_daily_mean_min_topography_2031-2040_CurPol_ensmean_WGS84.tif'
  self.write(self.zone,[[1,1,2],[1,2,2]],'float32')
  self.write(self.pop,[[1,3,1],[1,1,0]],'float32')
  self.write(self.temp,[[5,15,20],[10,25,30]],'float32')
  self.write(self.uhi,[[1,2,3],[0,4,5]],'float32')
 def write(self,p,a,dtype):
  with rasterio.open(p,'w',driver='GTiff',height=2,width=3,count=1,crs='EPSG:4326',transform=from_origin(10,50,.01,.01),dtype=dtype) as s:s.write(np.array(a,dtype=dtype),1)
 def go(self,**k):
  params={'city':'Paris','member_inputs':{'warm_nights_20_days_per_year':self.temp,'nighttime_uhi_c':self.uhi},'zone_grid':self.zone,'population_grid':self.pop,'provider_scenario':'CurPol','statistic':'ensmean'}
  params.update(k)
  return aggregate_city_rasters(**params)
 def test_two_regions_two_metrics(self):
  a=self.go();self.assertEqual(len(a['rows']),4)
  r={(x['zone_id'],x['indicator']):x for x in a['rows']}
  self.assertAlmostEqual(r[(1,'warm_nights_20_days_per_year')]['mean'],12)
  self.assertEqual(r[(2,'warm_nights_20_days_per_year')]['mean'],22.5)
 def test_no_population(self):
  a=aggregate_city_rasters(city='Paris',member_inputs={'warm_nights_20_days_per_year':self.temp},zone_grid=self.zone,population_grid=None,provider_scenario='CurPol',statistic='ensmean')
  self.assertEqual(a['rows'][0]['weight_basis'],'equal_grid_cell')
 def test_refuses_pathway_alias(self):
  with self.assertRaises(ValueError):aggregate_city_rasters(city='Paris',member_inputs={'warm_nights_20_days_per_year':self.temp},zone_grid=self.zone,population_grid=self.pop,provider_scenario='PAS',statistic='ensmean')
 def test_bad_file_indicator(self):
  with self.assertRaises(ValueError):aggregate_city_rasters(city='Paris',member_inputs={'heatwave_days_per_year':self.temp},zone_grid=self.zone,population_grid=self.pop,provider_scenario='CurPol',statistic='ensmean')
 def test_bad_statistic(self):
  with self.assertRaises(ValueError):self.go(statistic='p99')
 def test_misaligned_population(self):
  bad=self.p/'misaligned.tif'
  with rasterio.open(bad,'w',driver='GTiff',height=2,width=3,count=1,crs='EPSG:3857',transform=from_origin(10,50,.01,.01),dtype='float32') as s:s.write(np.ones((2,3),dtype=np.float32),1)
  with self.assertRaises(ValueError):aggregate_city_rasters(city='Paris',member_inputs={'warm_nights_20_days_per_year':self.temp},zone_grid=self.zone,population_grid=bad,provider_scenario='CurPol',statistic='ensmean')
 def test_nan_grid_reject(self):
  self.write(self.zone,[[1,np.nan,2],[1,2,2]],'float32')
  with self.assertRaises(ValueError):self.go()
 def test_negative_counter_reject(self):
  self.write(self.temp,[[5,-15,20],[10,25,30]],'float32')
  with self.assertRaises(ValueError):self.go()
 def test_zenodo_source_underscore_decade(self):
  renamed=self.p/'T2M_nightover20_2031_2040_CurPol_ensmean.tif'
  renamed.write_bytes(self.temp.read_bytes())
  a=self.go(member_inputs={'warm_nights_20_days_per_year':renamed})
  self.assertEqual(len(a['rows']),2)
  self.assertEqual(a['provider_period'],'2031-2040')
 def test_zenodo_wrong_decade_rejected(self):
  renamed=self.p/'T2M_nightover20_2041_2050_CurPol_ensmean.tif'
  renamed.write_bytes(self.temp.read_bytes())
  with self.assertRaises(ValueError):self.go(member_inputs={'warm_nights_20_days_per_year':renamed})
 def test_source_provenance(self):
  a=self.go();self.assertEqual(len(a['inputs']['nighttime_uhi_c']['sha256']),64)
  self.assertEqual(a['status'],'RESEARCH_ONLY_NOT_RUNTIME')
  self.assertTrue(any('morphology' in q for q in a['limits']))
if __name__=='__main__':unittest.main()

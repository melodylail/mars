# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

import numpy as np

import mars.tensor as mt
from mars.learn.tests.integrated.base import LearnIntegrationTestBase
from mars.learn.contrib.pytorch import MarsDataset, MarsDistributedSampler
from mars.context import DistributedContext
from mars.session import new_session
from mars.utils import lazy_import

torch_installed = lazy_import('torch', globals=globals()) is not None


@unittest.skipIf(not torch_installed, 'pytorch not installed')
class Test(LearnIntegrationTestBase):
    def testDistributedDataset(self):
        service_ep = 'http://127.0.0.1:' + self.web_port
        scheduler_ep = '127.0.0.1:' + self.scheduler_port
        with new_session(service_ep) as sess:
            raw = np.random.rand(100, 200)
            data = mt.tensor(raw, chunk_size=40)
            data.execute(name='data', session=sess)

            with DistributedContext(scheduler_address=scheduler_ep, session_id=sess.session_id):
                dataset = MarsDataset('data')
                self.assertEqual(len(dataset), 100)

                sample = np.random.randint(0, 100, (10,))
                r1 = dataset[sample][0]
                np.testing.assert_array_equal(raw[sample], r1)

                sample = np.random.randint(0, 100, (10,))
                dataset.prefetch(sample)
                r2 = np.array([dataset[ind][0] for ind in sample])
                np.testing.assert_array_equal(raw[sample], r2)

    def testDistributedSampler(self, *_):
        service_ep = 'http://127.0.0.1:' + self.web_port
        scheduler_ep = '127.0.0.1:' + self.scheduler_port
        with new_session(service_ep) as sess:
            raw1 = np.random.rand(100, 200)
            data1 = mt.tensor(raw1, chunk_size=40)
            data1.execute(name='data1', session=sess)

            raw2 = np.random.rand(100,)
            data2 = mt.tensor(raw2, chunk_size=60)
            data2.execute(name='data2', session=sess)

            with DistributedContext(scheduler_address=scheduler_ep, session_id=sess.session_id):
                dataset = MarsDataset('data1', 'data2')
                self.assertEqual(len(dataset), 100)

                sampler = MarsDistributedSampler(dataset, num_replicas=1, rank=0)
                indices = sampler.generate_indices()
                r1 = np.array(dataset._get_data(indices)[0])
                r2 = np.array([dataset[ind][0] for ind in sampler])
                np.testing.assert_array_equal(r1, r2)

                r1 = np.array(dataset._get_data(indices)[1])
                r2 = np.array([dataset[ind][1] for ind in sampler])
                np.testing.assert_array_equal(r1, r2)

                self.assertEqual(len(sampler), 100)

                sampler.set_epoch(1)
                self.assertEqual(sampler.epoch, 1)

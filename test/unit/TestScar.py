import io
import os
import unittest.mock
import sys
import zipfile

from botocore.exceptions import ClientError
from scar import Scar
from unittest.mock import call

sys.path.append(".")
sys.path.append("..")

class TestScar(unittest.TestCase):
    
    capturedOutput = None

    def setUp(self):
        TestScar.capturedOutput = io.StringIO()
        sys.stdout = TestScar.capturedOutput        

    def tearDown(self):
        TestScar.capturedOutput.close()
        sys.stdout = sys.__stdout__
        
    def test_chunks(self):
        test_list = [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]
        chunks = Scar().chunks(test_list, 3)
        self.assertEqual(next(chunks), [1, 2, 3])
        self.assertEqual(next(chunks), [4, 5, 6])
        self.assertEqual(next(chunks), [7, 8, 9])
        self.assertEqual(next(chunks), [0])
        
    def test_chunks_empty(self):
        chunks = Scar().chunks([], 3)
        self.assertEqual(next(chunks), [])
        
    def test_chunks_big_chunk(self):
        chunks = Scar().chunks([1, 2, 3], 5)
        self.assertEqual(next(chunks), [1, 2, 3])        
        
    @unittest.mock.patch('scar.AwsClient')        
    def test_get_aws_client(self, mock_aws_client):
        Scar().get_aws_client()
        self.assertEqual(mock_aws_client.call_count, 1)
        self.assertEqual(mock_aws_client.call_args, call())
        
    def test_parse_logs(self):
        test_logs = 'test first line\nSTART 42\ntest message to log\nsecond line to log\nREPORT 42\nlast line not log\n'
        result = Scar().parse_aws_logs(test_logs, '42')
        self.assertEqual(result, 'START 42\ntest message to log\nsecond line to log\nREPORT 42\n')
        
    def test_parse_logs_empty_log(self):
        test_logs = ''
        result = Scar().parse_aws_logs(test_logs, '42')
        self.assertEqual(result, None)
        
    def test_parse_logs_none_log(self):
        result = Scar().parse_aws_logs(None, '42')
        self.assertEqual(result, None)        
        
    def test_parse_logs_diff_req_id(self):
        test_logs = 'test first line\nSTART 42\ntest message to log\nsecond line to log\nREPORT 42\nlast line not log\n'
        result = Scar().parse_aws_logs(test_logs, '40')
        self.assertEqual(result, None)
        
    def test_parse_logs_empty_req_id(self):
        test_logs = 'test first line\nSTART 42\ntest message to log\nsecond line to log\nREPORT 42\nlast line not log\n'
        result = Scar().parse_aws_logs(test_logs, '')
        self.assertEqual(result, 'START 42\ntest message to log\nsecond line to log\nREPORT 42\n')            

    def test_parse_logs_none_req_id(self):
        result = Scar().parse_aws_logs('test', None)
        self.assertEqual(result, None)
        
    def test_create_zip_file(self):
        test_file_path = os.path.dirname(os.path.abspath(__file__))
        zip_file_path = "%s/../../function.zip" % test_file_path
        Scar().create_zip_file('test')
        self.assertTrue(os.path.isfile(zip_file_path))
        self.assertEqual(zipfile.ZipFile(zip_file_path).namelist(), ['test.py', 'udocker', 'udocker-1.1.0-RC2.tar.gz'])
        os.remove(zip_file_path)
        
    def test_create_zip_file_with_script(self):
        test_file_path = os.path.dirname(os.path.abspath(__file__))
        zip_file_path = "%s/../../function.zip" % test_file_path
        Scar().create_zip_file('test', "%s/files/test_script.sh" % test_file_path)
        self.assertTrue(os.path.isfile(zip_file_path))
        self.assertEqual(zipfile.ZipFile(zip_file_path).namelist(), ['test.py', 'udocker', 'udocker-1.1.0-RC2.tar.gz', 'init_script.sh'])
        os.remove(zip_file_path)

    @unittest.mock.patch('scar.AwsClient.delete_resources')
    def test_rm(self, mock_delete_resources):
        args = Args()
        setattr(args, 'all', False)
        Scar().rm(args)
        self.assertEqual(mock_delete_resources.call_count, 1)        
        self.assertEqual(mock_delete_resources.call_args, call('test-name', False, True))
               
    @unittest.mock.patch('scar.AwsClient.delete_resources')               
    @unittest.mock.patch('scar.AwsClient.get_all_functions')
    def test_rm_all(self, mock_get_all_functions, mock_delete_resources):
        args = Args()
        setattr(args, 'all', True)
        mock_get_all_functions.return_value = [{'Configuration' : {'FunctionName' : 'test-name_1'}},
                                               {'Configuration' : {'FunctionName' : 'test-name_2'}}]
        Scar().rm(args)
        self.assertEqual(mock_get_all_functions.call_count, 1) 
        self.assertEqual(mock_delete_resources.call_count, 2)        
        self.assertTrue(call('test-name_1', False, True) in mock_delete_resources.mock_calls)
        self.assertTrue(call('test-name_2', False, True) in mock_delete_resources.mock_calls)             

    @unittest.mock.patch('scar.Scar.parse_run_response')               
    @unittest.mock.patch('scar.AwsClient.invoke_function')                 
    def test_launch_request_response_event(self, mock_aws_client, mock_parse_response):
        event = {'Records' : [{'s3' : {'object': {'key' : 'test'}}}]}
        mock_aws_client.invoke_function.return_value = 'invoke_return'
        Scar().launch_request_response_event('s3_test_file', event, mock_aws_client, Args())
        self.assertEqual(mock_parse_response.call_count, 1)
        self.assertTrue(call.invoke_function('test-name', 'RequestResponse',
                                             'Tail', '{"Records": [{"s3": {"object": {"key": "s3_test_file"}}}]}')
                 in mock_aws_client.mock_calls) 
        self.assertTrue(call('invoke_return', 'test-name', False, False, True) in mock_parse_response.mock_calls)
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue("Sending event for file 's3_test_file'" in output)
        
    @unittest.mock.patch('scar.Scar.parse_run_response')               
    @unittest.mock.patch('scar.AwsClient.invoke_function')                 
    def test_launch_async_event(self, mock_aws_client, mock_parse_response):
        event = {'Records' : [{'s3' : {'object': {'key' : 'test'}}}]}
        mock_aws_client.invoke_function.return_value = 'invoke_return'
        Scar().launch_async_event('s3_test_file', event, mock_aws_client, Args())
        self.assertEqual(mock_parse_response.call_count, 1)
        self.assertTrue(call.invoke_function('test-name', 'Event',
                                             'None', '{"Records": [{"s3": {"object": {"key": "s3_test_file"}}}]}')
                 in mock_aws_client.mock_calls) 
        self.assertTrue(call('invoke_return', 'test-name', True, False, True) in mock_parse_response.mock_calls)
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue("Sending event for file 's3_test_file'" in output)
        



    @unittest.mock.patch('scar.StringUtils.parse_log_ids')
    @unittest.mock.patch('scar.StringUtils.parse_base64_response_values')        
    @unittest.mock.patch('scar.StringUtils.parse_payload')    
    def test_parse_run_response_plain_text(self, mock_parse_payload, mock_parse_base64_response_values, mock_parse_log_ids):
        mock_parse_payload.return_value = 'test payload'
        mock_parse_base64_response_values.return_value = 'test base 64'
        mock_parse_log_ids.return_value = {'StatusCode' : '42',
                                           'Payload' : 'test payload',
                                           'LogGroupName' : 'test log group',
                                           'LogStreamName' : 'test log stream',
                                           'ResponseMetadata' : {'RequestId' : '99'},
                                           'Extra' : 'test_verbose'}
        Scar().parse_run_response('test_response', 'test_function', False, False, False)
        output = TestScar.capturedOutput.getvalue()
        self.assertEquals(output, 'SCAR: Request Id: 99\ntest payload\n\n')         

    @unittest.mock.patch('scar.Result')
    @unittest.mock.patch('scar.StringUtils.parse_log_ids')
    @unittest.mock.patch('scar.StringUtils.parse_base64_response_values')        
    @unittest.mock.patch('scar.StringUtils.parse_payload')    
    def test_parse_run_response_json(self, mock_parse_payload, mock_parse_base64_response_values, mock_parse_log_ids, mock_result):
        mock_parse_payload.return_value = 'test payload'
        mock_parse_base64_response_values.return_value = 'test base 64'
        mock_parse_log_ids.return_value = {'StatusCode' : '42',
                                           'Payload' : 'test payload',
                                           'LogGroupName' : 'test log group',
                                           'LogStreamName' : 'test log stream',
                                           'ResponseMetadata' : {'RequestId' : '99'},
                                           'Extra' : 'test_verbose'}
        Scar().parse_run_response('test_response', 'test_function', False, True, False)
        self.assertEqual(mock_result.call_count, 1)
        self.assertTrue(call().append_to_json('LambdaOutput', {'Payload': 'test payload',
                                                                'LogGroupName': 'test log group',
                                                                'LogStreamName': 'test log stream',
                                                                'StatusCode': '42',
                                                                'RequestId': '99'}) in mock_result.mock_calls)       
        self.assertTrue(call().print_results(json=True, verbose=False) in mock_result.mock_calls)

    @unittest.mock.patch('scar.Result')        
    @unittest.mock.patch('scar.StringUtils.parse_log_ids')
    @unittest.mock.patch('scar.StringUtils.parse_base64_response_values')        
    @unittest.mock.patch('scar.StringUtils.parse_payload')    
    def test_parse_run_response_verbose(self, mock_parse_payload, mock_parse_base64_response_values, mock_parse_log_ids, mock_result):
        mock_parse_payload.return_value = 'test payload'
        mock_parse_base64_response_values.return_value = 'test base 64'
        mock_parse_log_ids.return_value = {'StatusCode' : '42',
                                           'Payload' : 'test payload',
                                           'LogGroupName' : 'test log group',
                                           'LogStreamName' : 'test log stream',
                                           'ResponseMetadata' : {'RequestId' : '99'},
                                           'Extra' : 'test_verbose'}
        Scar().parse_run_response('test_response', 'test_function', False, False, True)
        self.assertEqual(mock_result.call_count, 1)
        self.assertTrue(call().append_to_verbose('LambdaOutput', {'LogGroupName': 'test log group',
                                                                   'ResponseMetadata': {'RequestId': '99'},
                                                                   'Payload': 'test payload',
                                                                   'LogStreamName': 'test log stream',
                                                                   'StatusCode': '42',
                                                                   'Extra': 'test_verbose'}) in mock_result.mock_calls)
        self.assertTrue(call().print_results(json=False, verbose=True) in mock_result.mock_calls)
        
        
    @unittest.mock.patch('scar.StringUtils.parse_payload')            
    def test_parse_run_response_async(self, mock_parse_payload):
        mock_parse_payload.return_value = {'StatusCode' : '42',
                                           'Payload' : 'test payload',
                                           'ResponseMetadata' : {'RequestId' : '99'},
                                           'Extra' : 'test_verbose'}
        Scar().parse_run_response('test_response', 'test_function', True, False, False)
        output = TestScar.capturedOutput.getvalue()
        self.assertEquals(output, "Function 'test_function' launched correctly\n\n")     

    @unittest.mock.patch('scar.Result')        
    @unittest.mock.patch('scar.StringUtils.parse_payload')            
    def test_parse_run_response_async_json(self, mock_parse_payload, mock_result):
        mock_parse_payload.return_value = {'StatusCode' : '42',
                                           'Payload' : 'test payload',
                                           'ResponseMetadata' : {'RequestId' : '99'},
                                           'Extra' : 'test_verbose'}
        Scar().parse_run_response('test_response', 'test_function', True, True, False)
        self.assertEqual(mock_result.call_count, 1)
        self.assertTrue(call().append_to_json('LambdaOutput', {'StatusCode': '42',
                                                               'RequestId': '99'}) in mock_result.mock_calls)       
        self.assertTrue(call().print_results(json=True, verbose=False) in mock_result.mock_calls)        
        
    @unittest.mock.patch('scar.Result')        
    @unittest.mock.patch('scar.StringUtils.parse_payload')            
    def test_parse_run_response_async_verbose(self, mock_parse_payload, mock_result):
        mock_parse_payload.return_value = {'StatusCode' : '42',
                                           'Payload' : 'test payload',
                                           'ResponseMetadata' : {'RequestId' : '99'},
                                           'Extra' : 'test_verbose'}
        Scar().parse_run_response('test_response', 'test_function', True, False, True)
        self.assertEqual(mock_result.call_count, 1)
        self.assertTrue(call().append_to_verbose('LambdaOutput', {'StatusCode' : '42',
                                                                  'Payload' : 'test payload',
                                                                  'ResponseMetadata' : {'RequestId' : '99'},
                                                                  'Extra' : 'test_verbose'}) in mock_result.mock_calls)
        self.assertTrue(call().print_results(json=False, verbose=True) in mock_result.mock_calls)          
        
        
    @unittest.mock.patch('scar.StringUtils.parse_payload')        
    def test_parse_run_response_function_error_function(self, mock_parse_payload):
        mock_parse_payload.return_value = {'FunctionError' : '42',
                                           'Payload' : 'error payload'}
        with self.assertRaises(SystemExit):
            Scar().parse_run_response('test_response', 'test_function', True, False, False)
        output = TestScar.capturedOutput.getvalue()
        self.assertEquals(output, "Error in function response: error payload\n")         
        
    @unittest.mock.patch('scar.StringUtils.parse_payload')        
    def test_parse_run_response_function_error_time_out(self, mock_parse_payload):
        mock_parse_payload.return_value = {'FunctionError' : '42',
                                           'Payload' : 'Task timed out after 280 seconds'}
        with self.assertRaises(SystemExit):
            Scar().parse_run_response('test_response', 'test_function', True, False, False)
        output = TestScar.capturedOutput.getvalue()
        self.assertEquals(output, "Error: Function 'test_function' timed out after 280 seconds\n")
        
    @unittest.mock.patch('scar.StringUtils.parse_payload')        
    def test_parse_run_response_function_error_time_out_json(self, mock_parse_payload):
        mock_parse_payload.return_value = {'FunctionError' : '42',
                                           'Payload' : 'Task timed out after 280 seconds'}
        with self.assertRaises(SystemExit):
            Scar().parse_run_response('test_response', 'test_function', True, True, False)
        output = TestScar.capturedOutput.getvalue()
        self.assertEquals(output, '{"Error": "Function \'test_function\' timed out after 280 seconds"}\n')

    @unittest.mock.patch('scar.AwsClient.get_log')        
    def test_log(self, mock_aws_client):
        mock_aws_client.return_value.filter_log_events.side_effect = [{'events' : [{'message':'val1', 'timestamp':'123456'},
                                                                                   {'message':'val3', 'timestamp':'123458'},
                                                                                   {'message':'val2', 'timestamp':'123457'}],
                                                                       'nextToken' : '1'},
                                                                      {'events' : [{'message':'val6', 'timestamp':'123461'},
                                                                                   {'message':'val5', 'timestamp':'123460'},
                                                                                   {'message':'val4', 'timestamp':'123459'}],
                                                                       'nextToken' : '2'},
                                                                      {'events' : [{'message':'val7', 'timestamp':'123462'},
                                                                                   {'message':'val8', 'timestamp':'123463'},
                                                                                   {'message':'val9', 'timestamp':'123464'}]}]
        args = Args()
        setattr(args, 'log_stream_name', False)
        setattr(args, 'request_id', False)
        Scar().log(args)
        output = TestScar.capturedOutput.getvalue()
        self.assertEquals(output, 'val1val2val3val4val5val6val7val8val9\n')
    
    @unittest.mock.patch('scar.AwsClient.get_log')        
    def test_log_with_log_stream_name(self, mock_aws_client):
        mock_aws_client.return_value.get_log_events.return_value = {'events' : [{'message':'val1'},
                                                                                {'message':'val2'},
                                                                                {'message':'val3'}]}
        args = Args()
        setattr(args, 'log_stream_name', True)
        setattr(args, 'request_id', False)
        Scar().log(args)
        output = TestScar.capturedOutput.getvalue()
        self.assertEqual(output, 'val1val2val3\n')
        

    @unittest.mock.patch('scar.Scar.parse_aws_logs')
    @unittest.mock.patch('scar.AwsClient.get_log')        
    def test_log_with_request_id(self, mock_aws_client, mock_parse_aws_logs):
        mock_aws_client.return_value.get_log_events.return_value = {'events' : [{'message':'val1'},
                                                                                {'message':'val2'},
                                                                                {'message':'val3'}]}
        args = Args()
        setattr(args, 'log_stream_name', True)
        setattr(args, 'request_id', 42)
        Scar().log(args)
        self.assertEqual(mock_parse_aws_logs.call_count, 1)
        self.assertTrue(call('val1val2val3', 42) in mock_parse_aws_logs.mock_calls)
        
    @unittest.mock.patch('scar.AwsClient.get_log')
    def test_log_error(self, mock_aws_client):
        mock_aws_client.side_effect = ClientError({'Error' : {'Code' : '42', 'Message' : 'test_message'}}, 'test2')
        args = Args()
        setattr(args, 'log_stream_name', True)
        Scar().log(args)
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue('An error occurred (42) when calling the test2 operation: test_message' in output)

    @unittest.mock.patch('scar.AwsClient.get_all_functions')
    def test_ls(self, mock_get_all_functions):
        mock_get_all_functions.return_value = [{'Configuration' : {
                                                    'FunctionName' : 'test_function',
                                                    'MemorySize' : '512',
                                                    'Timeout' : '300',
                                                    'Environment' : { 'Variables' : {'IMAGE_ID' : 'test_image'}}},
                                               'Extra' : 'test_verbose'},
                                               {'Configuration' : {
                                                    'FunctionName' : 'test_function_2',
                                                    'MemorySize' : '2014',
                                                    'Timeout' : '200',
                                                    'Environment' : { 'Variables' : {'IMAGE_ID' : 'test_image_2'}}},
                                               'Extra' : 'test_verbose_2'}
                                               ]
        args = Args()
        args.verbose = False
        Scar().ls(args)
        output = TestScar.capturedOutput.getvalue()
        result_table = 'NAME               MEMORY    TIME  IMAGE_ID\n'
        result_table += '---------------  --------  ------  ------------\n'
        result_table += 'test_function         512     300  test_image\n'
        result_table += 'test_function_2      2014     200  test_image_2\n'
        self.assertEqual(output, result_table)

    @unittest.mock.patch('scar.Scar.get_aws_client')
    def test_ls_error(self, mock_aws_client):
        mock_aws_client.side_effect = ClientError({'Error' : {'Code' : '42', 'Message' : 'test_message'}}, 'test2')
        Scar().ls(Args())
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue('Error listing the resources:' in output)          
        self.assertTrue('An error occurred (42) when calling the test2 operation: test_message' in output)        
                                  
    def test_init_name_error(self):
        args = Args()
        args.name = 'error_name.'
        with self.assertRaises(SystemExit):
            Scar().init(args)        
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue('{"Error": "Function name \'error_name.\' is not valid."}\n' in output)
        args.verbose = False
        with self.assertRaises(SystemExit):
            Scar().init(args)        
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue("Error: Function name 'error_name.' is not valid.\n" in output)            
        
    @unittest.mock.patch('scar.AwsClient')   
    def test_init_error(self, mock_aws_client):
        mock_aws_client.return_value.get_lambda.return_value.create_function.side_effect = ClientError({'Error' : {'Code' : '42', 'Message' : 'test_message'}}, 'test2')
        args = Args()
        args.verbose = False
        with self.assertRaises(SystemExit):
            Scar().init(args)        
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue("Error initializing lambda function:" in output)
        self.assertTrue("An error occurred (42) when calling the test2 operation: test_message" in output)  

    @unittest.mock.patch('scar.AwsClient')   
    def test_init(self, mock_aws_client):
        mock_aws_client.return_value.get_access_key.return_value = 'test_key'
        mock_aws_client.return_value.get_lambda.return_value.create_function.return_value = {'FunctionArn':'arn123',
                                                                                            'Timeout':'300',
                                                                                            'MemorySize':'512',
                                                                                            'FunctionName':'f1-name',
                                                                                            'Extra1':'e1',
                                                                                            'Extra2':'e2'}
        args = Args()
        args.verbose = False
        Scar().init(args)        
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue("Function 'test-name' successfully created.\n" in output)
        self.assertTrue("Log group '/aws/lambda/test-name' successfully created.\n\n" in output)
        
    @unittest.mock.patch('scar.AwsClient')   
    def test_init_retention_policy_error(self, mock_aws_client):
        mock_aws_client.return_value.get_access_key.return_value = 'test_key'
        mock_aws_client.return_value.get_lambda.return_value.create_function.return_value = {'FunctionArn':'arn123',
                                                                                            'Timeout':'300',
                                                                                            'MemorySize':'512',
                                                                                            'FunctionName':'f1-name',
                                                                                            'Extra1':'e1',
                                                                                            'Extra2':'e2'}
        mock_aws_client.return_value.get_log.return_value.put_retention_policy.side_effect = ClientError({'Error' : {'Code' : '42', 'Message' : 'test_message'}}, 'test2')
        
        args = Args()
        args.verbose = False
        Scar().init(args)        
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue("Error setting log retention policy:" in output)
        self.assertTrue("An error occurred (42) when calling the test2 operation: test_message" in output)  

    @unittest.mock.patch('scar.AwsClient')   
    def test_init_event_source_error(self, mock_aws_client):
        mock_aws_client.return_value.get_access_key.return_value = 'test_key'
        mock_aws_client.return_value.get_lambda.return_value.create_function.return_value = {'FunctionArn':'arn123',
                                                                                            'Timeout':'300',
                                                                                            'MemorySize':'512',
                                                                                            'FunctionName':'f1-name',
                                                                                            'Extra1':'e1',
                                                                                            'Extra2':'e2'}
        mock_aws_client.return_value.check_and_create_s3_bucket.side_effect = ClientError({'Error' : {'Code' : '42', 'Message' : 'test_message'}}, 'test2')
        
        args = Args()
        args.verbose = False
        args.event_source = True       
        Scar().init(args)        
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue("Error creating the event source:" in output)
        self.assertTrue("An error occurred (42) when calling the test2 operation: test_message" in output)  

    @unittest.mock.patch('scar.AwsClient')   
    def test_init_log_group_error(self, mock_aws_client):
        mock_aws_client.return_value.get_access_key.return_value = 'test_key'
        mock_aws_client.return_value.get_lambda.return_value.create_function.return_value = {'FunctionArn':'arn123',
                                                                                            'Timeout':'300',
                                                                                            'MemorySize':'512',
                                                                                            'FunctionName':'f1-name',
                                                                                            'Extra1':'e1',
                                                                                            'Extra2':'e2'}
        mock_aws_client.return_value.get_log.return_value.create_log_group.side_effect = ClientError({'Error' : {'Code' : '42', 'Message' : 'test_message'}}, 'test2')
        
        args = Args()
        args.verbose = False
        Scar().init(args)        
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue("Error creating log groups:" in output)
        self.assertTrue("An error occurred (42) when calling the test2 operation: test_message" in output) 

    @unittest.mock.patch('scar.AwsClient')   
    def test_init_existing_log_group(self, mock_aws_client):
        mock_aws_client.return_value.get_access_key.return_value = 'test_key'
        mock_aws_client.return_value.get_lambda.return_value.create_function.return_value = {'FunctionArn':'arn123',
                                                                                            'Timeout':'300',
                                                                                            'MemorySize':'512',
                                                                                            'FunctionName':'f1-name',
                                                                                            'Extra1':'e1',
                                                                                            'Extra2':'e2'}
        mock_aws_client.return_value.get_log.return_value.create_log_group.side_effect = ClientError({'Error' : {'Code' : 'ResourceAlreadyExistsException', 'Message' : 'test_message'}}, 'test2')
        
        args = Args()
        args.verbose = False
        Scar().init(args)        
        output = TestScar.capturedOutput.getvalue()
        self.assertTrue("Function 'test-name' successfully created.\n" in output)
        self.assertTrue("Warning: Using existent log group '/aws/lambda/test-name'\n\n" in output) 

    @unittest.mock.patch('scar.Scar.parse_run_response')
    @unittest.mock.patch('scar.AwsClient')                    
    def test_run(self, mock_aws_client, mock_parse_response):
        args = Args()
        args.verbose = False
        Scar().run(args)        
        self.assertEqual(mock_aws_client.call_count, 1)
        self.assertEqual(mock_parse_response.call_count, 1)
        self.assertTrue(call().check_function_name_not_exists('test-name', False) in mock_aws_client.mock_calls)
        self.assertTrue(call().invoke_function('test-name', 'RequestResponse', 'Tail', '{}') in mock_aws_client.mock_calls)  

    @unittest.mock.patch('scar.Scar.launch_async_event')
    @unittest.mock.patch('scar.Scar.launch_request_response_event')
    @unittest.mock.patch('scar.AwsClient')                    
    def test_run_event_source(self, mock_aws_client, mock_launch_request_response_event, mock_launch_async_event):
        mock_aws_client.return_value.get_s3_file_list.return_value = ['test_file_1','test_file_2','test_file_3','test_file_4']
        args = Args()
        args.verbose = False
        args.event_source = 'test_bucket'
        Scar().run(args)        
        self.assertEqual(mock_aws_client.call_count, 1)
        self.assertTrue(call().check_function_name_not_exists('test-name', False) in mock_aws_client.mock_calls)
        self.assertTrue(call().get_s3_file_list('test_bucket') in mock_aws_client.mock_calls)    
        self.assertEqual(mock_launch_request_response_event.call_count, 1)
        self.assertEqual(mock_launch_async_event.call_count, 3)          
                        
if __name__ == '__main__':
    unittest.main()
    
class Args(object):
    name = 'test-name'
    json = False
    verbose = True
    script = None
    memory = None
    time = None
    description = None
    image_id = None
    lambda_role = None
    time_threshold = None
    env = None
    event_source = None
    async = None
    cont_args = None
    recursive = False    

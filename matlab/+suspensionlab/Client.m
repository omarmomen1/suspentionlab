classdef Client < handle
    % CLIENT Typed MATLAB SDK Client for SuspensionLab PRO API.
    %
    % SuspensionLab PRO Industrial CAE Toolbox
    %
    % Features:
    %   - Token and API Key authentication
    %   - Synchronous and asynchronous simulations
    %   - Telemetry dataset retrieval and parsing
    %   - Background optimization job submission and polling
    %   - Comprehensive CAE export (FMI 2.0 FMU, Simulink .m, MSC ADAMS)
    
    properties
        ApiKey   (1,:) char
        BaseUrl  (1,:) char = 'http://localhost:8000'
        Timeout  (1,1) double = 30.0
    end
    
    methods
        function obj = Client(apiKey, baseUrl, timeout)
            % CLIENT Initialize client with credentials
            if nargin >= 1, obj.ApiKey = apiKey; end
            if nargin >= 2, obj.BaseUrl = rtrim(baseUrl, '/'); end
            if nargin >= 3, obj.Timeout = timeout; end
        end
        
        function result = simulateQuarterCar(obj, params, profile)
            % SIMULATEQUARTERCAR Run 2-DOF Quarter Car dynamic simulation.
            %
            % Parameters:
            %   params  : suspensionlab.QuarterCarParams or struct
            %   profile : suspensionlab.RoadProfile or struct
            if isa(params, 'suspensionlab.QuarterCarParams')
                paramsStruct = params.toStruct();
            else
                paramsStruct = params;
            end
            
            if nargin < 3 || isempty(profile)
                profile = suspensionlab.RoadProfile();
            end
            if isa(profile, 'suspensionlab.RoadProfile')
                profileStruct = profile.toStruct();
            else
                profileStruct = profile;
            end
            
            payload = struct('params', paramsStruct, 'profile', profileStruct);
            resp = obj.sendRequest('POST', '/api/v1/simulate/quarter', payload);
            result = suspensionlab.SimulationResult(resp);
        end
        
        function result = simulateFullCar(obj, params, profile)
            % SIMULATEFULLCAR Run 7-DOF Full Car ride simulation.
            if isa(params, 'suspensionlab.FullCarParams')
                paramsStruct = params.toStruct();
            else
                paramsStruct = params;
            end
            
            if nargin < 3 || isempty(profile)
                profile = suspensionlab.RoadProfile();
            end
            if isa(profile, 'suspensionlab.RoadProfile')
                profileStruct = profile.toStruct();
            else
                profileStruct = profile;
            end
            
            payload = struct('params', paramsStruct, 'profile', profileStruct);
            resp = obj.sendRequest('POST', '/api/v1/simulate/full-car', payload);
            result = suspensionlab.SimulationResult(resp);
        end
        
        function data = getTelemetry(obj, datasetId, options)
            % GETTELEMETRY Retrieve telemetry channels for given dataset.
            endpoint = sprintf('/api/v1/telemetry/%s', datasetId);
            if nargin >= 3 && isstruct(options)
                endpoint = [endpoint, '?', obj.encodeQuery(options)];
            end
            data = obj.sendRequest('GET', endpoint);
        end
        
        function job = submitOptimization(obj, requestPayload)
            % SUBMITOPTIMIZATION Submit a multi-objective optimization sweep.
            resp = obj.sendRequest('POST', '/api/v1/optimize/pareto', requestPayload);
            job = suspensionlab.OptimizationResult(resp);
        end
        
        function res = getResults(obj, jobId)
            % GETRESULTS Inquire status/results of an asynchronous job.
            endpoint = sprintf('/api/v1/jobs/%s', jobId);
            raw = obj.sendRequest('GET', endpoint);
            res = suspensionlab.OptimizationResult(raw);
        end
        
        function res = pollJob(obj, jobId, pollInterval, timeout)
            % POLLJOB Poll job until complete, failed, or timed out.
            if nargin < 3, pollInterval = 1.0; end
            if nargin < 4, timeout = 60.0; end
            
            t0 = tic;
            while toc(t0) < timeout
                res = obj.getResults(jobId);
                if strcmp(res.Status, 'completed') || strcmp(res.Status, 'failed')
                    return;
                end
                pause(pollInterval);
            end
            error('Client:Timeout', 'Job %s exceeded polling timeout of %.1f s', jobId, timeout);
        end
        
        function report = getReport(obj, reportId, format)
            % GETREPORT Retrieve generated engineering decision report.
            if nargin < 3, format = 'json'; end
            endpoint = sprintf('/api/v1/reports/%s?format=%s', reportId, format);
            report = obj.sendRequest('GET', endpoint);
        end
        
        function savedPath = exportCAE(obj, exportType, params, outputPath)
            % EXPORTCAE Download production CAE models (FMU, Simulink, ADAMS).
            %
            % Parameters:
            %   exportType : 'fmu', 'simulink', 'adams_adm', 'adams_cmd', 'adams_py'
            %   params     : suspensionlab.FullCarParams or QuarterCarParams
            %   outputPath : destination file path
            
            switch lower(exportType)
                case 'fmu'
                    endpoint = '/api/v1/export/fmu';
                    isBinary = true;
                    payload = [];
                case 'simulink'
                    endpoint = '/api/v1/export/simulink';
                    isBinary = false;
                    payload = params.toStruct();
                case {'adams', 'adams_adm'}
                    endpoint = '/api/v1/export/adams?export_format=adm';
                    isBinary = false;
                    payload = params.toStruct();
                case 'adams_cmd'
                    endpoint = '/api/v1/export/adams?export_format=cmd';
                    isBinary = false;
                    payload = params.toStruct();
                case 'adams_py'
                    endpoint = '/api/v1/export/adams?export_format=py';
                    isBinary = false;
                    payload = params.toStruct();
                otherwise
                    error('Client:UnknownExport', 'Unknown CAE export type: %s', exportType);
            end
            
            rawBytes = obj.sendRawRequest('POST', endpoint, payload, isBinary);
            fid = fopen(outputPath, 'wb');
            if fid == -1
                error('Client:FileWriteError', 'Could not open %s for writing.', outputPath);
            end
            fwrite(fid, rawBytes);
            fclose(fid);
            savedPath = outputPath;
        end
    end
    
    methods (Access = private)
        function resp = sendRequest(obj, method, endpoint, payload)
            % SENDREQUEST Perform authenticated JSON HTTP request
            url = [obj.BaseUrl, endpoint];
            options = weboptions(...
                'HeaderFields', {'X-API-Key', obj.ApiKey; 'Content-Type', 'application/json'}, ...
                'Timeout', obj.Timeout, ...
                'MediaType', 'application/json' ...
            );
            
            try
                if strcmpi(method, 'POST')
                    resp = webwrite(url, payload, options);
                else
                    resp = webread(url, options);
                end
            catch ME
                error('Client:HttpError', 'SuspensionLab API %s %s failed: %s', ...
                    method, endpoint, ME.message);
            end
        end
        
        function raw = sendRawRequest(obj, method, endpoint, payload, isBinary)
            % SENDRAWREQUEST Fetch raw binary or text response
            url = [obj.BaseUrl, endpoint];
            if isBinary
                options = weboptions(...
                    'HeaderFields', {'X-API-Key', obj.ApiKey}, ...
                    'Timeout', obj.Timeout, ...
                    'ContentType', 'binary' ...
                );
            else
                options = weboptions(...
                    'HeaderFields', {'X-API-Key', obj.ApiKey; 'Content-Type', 'application/json'}, ...
                    'Timeout', obj.Timeout, ...
                    'ContentType', 'text' ...
                );
            end
            
            if strcmpi(method, 'POST')
                if isempty(payload)
                    raw = webwrite(url, struct(), options);
                else
                    raw = webwrite(url, payload, options);
                end
            else
                raw = webread(url, options);
            end
        end
        
        function qs = encodeQuery(~, s)
            fields = fieldnames(s);
            parts = cell(size(fields));
            for i = 1:length(fields)
                parts{i} = sprintf('%s=%s', fields{i}, char(string(s.(fields{i}))));
            end
            qs = strjoin(parts, '&');
        end
    end
end

function str = rtrim(str, charToTrim)
    while ~isempty(str) && str(end) == charToTrim
        str(end) = [];
    end
end

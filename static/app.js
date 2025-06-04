document.addEventListener('DOMContentLoaded', () => {
    const uploadForm = document.getElementById('uploadForm');
    const statusDiv = document.getElementById('status');
    const traceDiv = document.getElementById('trace');
    let pollInterval = null;

    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const file = document.getElementById('file').files[0];
        
        if (!file) {
            showError('Please select a file');
            return;
        }

        // Reset UI
        statusDiv.innerHTML = '<span class="processing">Processing...</span>';
        traceDiv.innerHTML = '';
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch('/process', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.status === 'processing') {
                statusDiv.innerHTML = `<span class="processing">Processing started. Process ID: ${data.process_id}</span>`;
                startPolling(data.process_id);
            }
        } catch (error) {
            showError(error.message);
        }
    });

    function startPolling(processId) {
        if (pollInterval) {
            clearInterval(pollInterval);
        }

        pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/status/${processId}`);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();
                updateTrace(data);

                if (data.status === 'completed' || data.status === 'error') {
                    clearInterval(pollInterval);
                    updateStatus(data.status);
                }
            } catch (error) {
                clearInterval(pollInterval);
                showError(error.message);
            }
        }, 1000);
    }

    function updateTrace(data) {
        const formattedData = JSON.stringify(data, null, 2);
        traceDiv.innerHTML = `<pre>${formattedData}</pre>`;
    }

    function updateStatus(status) {
        const statusClass = status === 'completed' ? 'success' : 'error';
        statusDiv.innerHTML = `<span class="${statusClass}">Processing ${status}</span>`;
    }

    function showError(message) {
        statusDiv.innerHTML = `<span class="error">Error: ${message}</span>`;
    }
}); 
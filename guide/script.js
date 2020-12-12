const PATTERN = /[A-Z]{3}/;


function admit(value) {
	let name = value.toUpperCase();
	if (PATTERN.test(name)) {
		localStorage.setItem('name', name);
		document.getElementById('link').href = '/morse?name=' + name;
		fetch('/checkname/' + name).then(function(response) {
			switch (response.status) {
				case 200:
				case 403:
					show('ready', response.status == 200);
					show('taken', response.status == 403);
					show('join', true);
					break;
				default:
					show('error', true);
			}
		});
	}
}

function show(id, state) {
	document.getElementById(id).classList.toggle('hidden', !state);
}

window.onload = function() {
	admit(document.getElementById('callsign').value);
};

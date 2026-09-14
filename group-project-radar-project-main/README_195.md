# Distributed mmWave Radar Network for Real Time 2D Floor Visualization

[![CI](https://github.com/SJSU-CMPE-195/group-project-radar-project/actions/workflows/ci.yml/badge.svg)](https://github.com/SJSU-CMPE-195/group-project-radar-project/actions/workflows/ci.yml)

> A distributed mmWave radar system that fuses point clouds from multiple sensors to visualize real time floor activity.

## Team

|      Name      |                      GitHub                      |          Email          |
|----------------|--------------------------------------------------|-------------------------|
| Andrew Bertch  | [@SuzumeHiroko](https://github.com/SuzumeHiroko) | andrew.bertch@sjsu.edu  |
| Camden Forbes  | [@CamdenForbes](https://github.com/CamdenForbes) | camden.forbes@sjsu.edu  |
| Daniel Gebran  | [@DanielGeb22](https://github.com/DanielGeb22)   | daniel.gebran@sjsu.edu  |
| Evan Alekseyev | [@ealekseyev](https://github.com/ealekseyev)     | evan.alekseyev@sjsu.edu |

**Advisor:** [Jahan Ghofraniha]

---

## Problem Statement

Using cameras to track activity and occupancy can be privacy invasive and is sensitive to lighting/obstructions. In lab and sports setting, there is a need for a reliable way to observe motion and occupancy for validation, safety, and analytics without recording identifiable video

## Solution

Our solution is to use a distributed mmWave radar network using multiple TI IWR6843AOP radar nodes and sensor fusion to produce a real time 2D floor visualization. Each node performs local processing and streams data for fusion to allow for live visualization and real time monitoring.

### Key Features

- Multi-node mmWave radar sensing
- Real-time sensor fusion into a unified 2D floor map
- Live visualization with secure API access and local logging

---

## Demo

Viewer Demo: https://drive.google.com/file/d/1ZhUAr6apMnaaxnAqaIU19VteoEP1WskP/view?usp=drivesdk
AWS Demo: https://drive.google.com/file/d/1fgauu75wf3KLxOKs-L5V7Blj0IiSIqpF/view?usp=drive_link

**Live Demo:** [URL if deployed]

---

## Screenshots

| Feature | Screenshot |
|---------|------------|
| [Feature 1] | ![Screenshot](docs/screenshots/feature1.png) |
| [Feature 2] | ![Screenshot](docs/screenshots/feature2.png) |

---

## Tech Stack

| Category | Technology |
|----------|------------|
| Frontend | |
| Backend | |
| Database | |
| Deployment | |

---

## Getting Started

### Prerequisites

- TI IWR6843AOP radar 
- Raspberry Pi Zero W 2 
- Python 3.13+ 
- pip 24.0+ 

### Installation

```bash
# Clone the repository
git clone https://github.com//group-project-radar-project.git
cd group-project-radar-project

# Run the installer (sets up venv, dependencies, systemd service, and auto-login)
sudo bash install/install.sh
```

### Running Locally

```bash
python src/main.py
```

### Running Tests

```bash
# Offline tests (no hardware required)
pytest tests/test_raw_serial.py tests/test_viewer_simulated_radar.py --tb=short

# With coverage report
pytest tests/test_raw_serial.py tests/test_viewer_simulated_radar.py --cov=src --cov-report=term-missing

# Lint and format checks
flake8 src/ tests/
black --check src/ tests/ --line-length 100
```

> Hardware tests in `tests/radar_interface/` require a physical IWR6843AOP EVM + Raspberry Pi.
> Results are recorded manually in [`docs/system_test_summary.md`](docs/system_test_summary.md).

---

## API Reference

<details>
<summary>Click to expand API endpoints</summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/resource` | Get all resources |
| GET | `/api/resource/:id` | Get resource by ID |
| POST | `/api/resource` | Create new resource |
| PUT | `/api/resource/:id` | Update resource |
| DELETE | `/api/resource/:id` | Delete resource |

</details>

---

## Project Structure

```
.
├── cad/                 # Hardware CAD files (sensor mounts, enclosures)
├── docs/                # Documentation and design assets
├── examples/            # Example scripts and usage demos
├── firmware/            # TI IWR6843AOP radar firmware / chirp configs
├── install/             # Installer scripts and systemd service unit
├── logs/                # Runtime log output (gitignored)
├── src/                 # Python source code
│   ├── main.py          # Entry point — arg parsing, radar + viewer orchestration
│   ├── radar.py         # RadarController — serial comms, frame parsing, health checks
│   ├── viewer.py        # PointCloudViewer3D — 4-quadrant matplotlib visualization
│   └── config.py        # Typed config loader — reads config.yaml into frozen dataclasses
├── tests/               # Unit and integration tests
├── config.yaml          # Default runtime configuration
├── requirements.txt     # Python dependencies
└── README.md
```

---

## Contributing

1. Create a feature branch (`git checkout -b feature/amazing-feature`)
2. Commit your changes (`git commit -m 'Add amazing feature'`)
3. Push to the branch (`git push origin feature/amazing-feature`)
4. Open a Pull Request

### Branch Naming

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring

### Commit Messages

Use clear, descriptive commit messages:
- `Add user authentication endpoint`
- `Fix database connection timeout issue`
- `Update README with setup instructions`

---

## Acknowledgments

- [Resource/Library/Person]
- [Resource/Library/Person]

---

## License

This project is licensed under the <FILL IN> License - see the [LICENSE](LICENSE) file for details.

---

*CMPE 195A/B - Senior Design Project | San Jose State University | Spring 2026*

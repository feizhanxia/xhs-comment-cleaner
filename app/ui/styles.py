APP_STYLESHEET = r"""
QWidget {
    background: #F5F6F8;
    color: #17181C;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 16px;
}

QMainWindow { background: #F5F6F8; }
QLabel { background: transparent; }

QLabel#eyebrow {
    color: #FF2442;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#title {
    color: #111216;
    font-size: 30px;
    font-weight: 700;
}
QLabel#subtitle, QLabel#muted {
    color: #6D7179;
    font-size: 15px;
}
QLabel#sectionTitle {
    color: #202126;
    font-size: 17px;
    font-weight: 700;
}
QLabel#metricValue {
    color: #16171B;
    font-size: 31px;
    font-weight: 700;
}
QLabel#metricLabel {
    color: #7B7F87;
    font-size: 14px;
}
QLabel#statusTitle {
    color: #202126;
    font-size: 18px;
    font-weight: 700;
}
QLabel#statusText {
    color: #646870;
    font-size: 15px;
}

QFrame#surface {
    background: #FFFFFF;
    border: 1px solid #E7E9ED;
    border-radius: 18px;
}
QFrame#statusDot {
    background: #A7ABB2;
    border-radius: 6px;
}
QFrame#divider {
    background: #ECEEF1;
    border: none;
    min-width: 1px;
    max-width: 1px;
}

QPushButton {
    background: #FFFFFF;
    color: #24262B;
    border: 1px solid #D9DCE1;
    min-height: 46px;
    padding: 0 20px;
    border-radius: 11px;
    font-size: 15px;
    font-weight: 650;
}
QPushButton[variant="primary"] {
    background: #FF2442;
    color: #FFFFFF;
    border: 1px solid #FF2442;
}
QPushButton[variant="primary"]:hover { background: #E91F3B; border-color: #E91F3B; }
QPushButton[variant="primary"]:pressed { background: #C91832; border-color: #C91832; }
QPushButton[variant="secondary"] {
    background: #FFFFFF;
    color: #24262B;
    border: 1px solid #D9DCE1;
}
QPushButton[variant="secondary"]:hover { background: #F7F8FA; border-color: #C6CAD0; }
QPushButton[variant="quiet"] {
    background: transparent;
    color: #5F636B;
    border: 1px solid transparent;
    padding: 0 10px;
}
QPushButton[variant="quiet"]:hover { background: #EBEDF1; color: #202126; }
QPushButton:disabled {
    background: #ECEEF1;
    color: #A3A6AD;
    border-color: #ECEEF1;
}

QProgressBar {
    min-height: 12px;
    max-height: 12px;
    border: none;
    border-radius: 6px;
    background: #ECEEF1;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    border-radius: 6px;
    background: #FF2442;
}

QDialog, QMessageBox { background: #F7F8FA; }
QTableWidget {
    background: #FFFFFF;
    alternate-background-color: #F8F9FA;
    border: 1px solid #E4E6EA;
    border-radius: 10px;
    gridline-color: #ECEEF1;
    selection-background-color: #FFE8EC;
    selection-color: #24262B;
}
QHeaderView::section {
    background: #F2F3F5;
    color: #5F636B;
    border: none;
    border-bottom: 1px solid #E4E6EA;
    padding: 10px;
    font-weight: 700;
}
"""

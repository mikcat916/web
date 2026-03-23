import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import type { RootState, AppDispatch } from '../store';
import { updateRobotState, updateSensorData } from '../store/robotSlice';
import { connectMqtt, disconnectMqtt } from '../utils/mqttClient';
import RobotStatusCard from '../components/RobotStatusCard';
import SensorPanel from '../components/SensorPanel';
import ControlButtons from '../components/ControlButtons';
import TemperatureChart from '../components/TemperatureChart';
import AlarmList from '../components/AlarmList';
import './Dashboard.css';
import MapPanel from '../components/MapPanel';
import { SensorData } from '../types/robot';

const Dashboard: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const { robotState, sensorData } = useSelector((state: RootState) => state.robot);
 const [tempData, setTempData] = useState<number[]>(() => {
  // 鐢熸垚鏇寸湡瀹炵殑鍒濆娓╁害鏁版嵁锛?4灏忔椂锛屾湁娉㈠姩锛?
  return Array.from({ length: 24 }, (_, i) => {
    const baseTemp = 22 + Math.sin(i * Math.PI / 12) * 3; // 姝ｅ鸡娉㈠姩
    const randomVariation = (Math.random() - 0.5) * 2; // 闅忔満娉㈠姩
    return Number((baseTemp + randomVariation).toFixed(1));
  });
});
(data: SensorData) => {
  dispatch(updateSensorData(data));
  // 娣诲姞鏇寸湡瀹炵殑娓╁害娉㈠姩
  const lastTemp = tempData[tempData.length - 1] || 24;
  const variation = (Math.random() - 0.5) * 1.5; // 鏇村皬鐨勬尝鍔?
  const newTemp = Number(Math.max(18, Math.min(32, lastTemp + variation)).toFixed(1));
  setTempData(prev => [...prev.slice(1), newTemp]);
}
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    console.log('鍒濆鍖?Dashboard...');
    
    // 杩炴帴 MQTT
    connectMqtt(
      (state) => {
        console.log('鏀跺埌鏈哄櫒浜虹姸鎬?', state);
        dispatch(updateRobotState(state));
      },
      (data) => {
        console.log('鏀跺埌浼犳劅鍣ㄦ暟鎹?', data);
        dispatch(updateSensorData(data));
        setTempData(prev => [...prev.slice(-23), data.temperature]);
      }
    );
    
    setIsConnected(true);

    // 妯℃嫙鏁版嵁鏇存柊锛堝鏋?MQTT 娌℃湁鏁版嵁锛?
    const timer = setInterval(() => {
      if (robotState && robotState.mode === 'inspecting') {
        dispatch(updateRobotState({
          battery: Math.max(10, robotState.battery - 0.5),
   
          task: {
            ...robotState.task,
            progress: Math.min(100, robotState.task.progress + 0.3)
          }
        }));
      }
    }, 3000);

    return () => {
      console.log('娓呯悊 Dashboard...');
      disconnectMqtt();
    
      clearInterval(timer);
      setIsConnected(false);
    };
  }, [dispatch]);

  // 鍔犺浇鐘舵€?
  if (!robotState || !sensorData) {
    return (
      <div className="dashboard-loading">
        <div className="loading-spinner"></div>
        <h2>System initializing...</h2>
        <p>Connecting to robot monitor service...</p>
        <div className="connection-status">
          <span className={`status-dot ${isConnected ? 'connected' : 'connecting'}`}></span>
          {isConnected ? 'MQTT connected' : 'MQTT connecting...'}
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <h1 className="dashboard-title">Machine Room Inspection Robot Monitor</h1>
        <div className="dashboard-status">
          <span className={`connection-badge ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? 'Online' : 'Offline'}
          </span>
          <span className="update-time">
            Last update: {new Date().toLocaleTimeString()}
          </span>
        </div>
      </header>

      <section className="dashboard-controls">
        <ControlButtons />
      </section>
    
    <section className="dashboard-map">
      <MapPanel />
    </section>

      <section className="dashboard-overview">
        <div className="dashboard-grid">
          <RobotStatusCard robotState={robotState} />
          <SensorPanel data={sensorData} />
        </div>
      </section>

      <section className="dashboard-analytics">
        <div className="dashboard-charts">
          <TemperatureChart temperatureData={tempData} />
          <AlarmList />
        </div>
      </section>
    </div>
  );
};

export default Dashboard;

